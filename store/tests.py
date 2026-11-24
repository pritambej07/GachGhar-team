from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Address
from .formatting import format_inr
from .models import Category, Order, Product, ProductVariant, SiteSettings, StockMovement

User = get_user_model()
JSON = {"HTTP_ACCEPT": "application/json"}


def make_product(name="Snake Plant", price="499.00", stock=10, active=True):
    category = Category.objects.get_or_create(name="Indoor Plants")[0]
    product = Product.objects.create(name=name, category=category, is_active=active)
    variant = ProductVariant.objects.create(product=product, name="6 inch", sku=f"SKU-{product.pk}-{name[:4]}",
                                            price=Decimal(price))
    if stock:
        StockMovement.objects.create(variant=variant, change=stock, reason=StockMovement.Reason.RESTOCK)
    return product, variant


class FormattingTests(TestCase):
    def test_indian_grouping(self):
        self.assertEqual(format_inr(Decimal("123456")), "₹1,23,456")
        self.assertEqual(format_inr(Decimal("499.50")), "₹499.50")
        self.assertEqual(format_inr(Decimal("1000")), "₹1,000")


class CatalogTests(TestCase):
    def test_pagination_links_use_one_query_delimiter(self):
        for index in range(13):
            make_product(f"Pagination plant {index}")

        response = self.client.get(reverse("store:products"))
        filtered_response = self.client.get(reverse("store:products"), {"q": "Pagination"})

        self.assertContains(response, 'href="?page=2"')
        self.assertContains(filtered_response, 'href="?q=Pagination&amp;page=2"')

    def test_clear_filters_keeps_search_query(self):
        make_product("Fern for testing")

        response = self.client.get(
            reverse("store:search"),
            {"q": "fern", "max_price": "100"},
        )

        self.assertContains(response, 'href="?q=fern"')

    def test_filtered_search_canonical_omits_query_string(self):
        response = self.client.get(
            reverse("store:search"),
            {"q": "fern", "max_price": "100"},
        )

        self.assertContains(response, '<link rel="canonical" href="http://testserver/search/">')

    def test_inactive_products_are_hidden(self):
        make_product("Visible plant")
        make_product("Hidden plant", active=False)
        response = self.client.get(reverse("store:products"))
        self.assertContains(response, "Visible plant")
        self.assertNotContains(response, "Hidden plant")

    def test_price_filter_uses_backend_data(self):
        make_product("Cheap fern", price="100.00")
        make_product("Costly palm", price="900.00")
        response = self.client.get(reverse("store:products"), {"max_price": "500"})
        self.assertContains(response, "Cheap fern")
        self.assertNotContains(response, "Costly palm")

    def test_fractional_price_filter_matches_decimal_prices(self):
        make_product("Fractional fern", price="99.99")
        make_product("Hundred palm", price="100.00")

        response = self.client.get(reverse("store:products"), {"max_price": "99.99"})

        self.assertContains(response, "Fractional fern")
        self.assertNotContains(response, "Hundred palm")
        self.assertContains(response, 'step="0.01"')

    def test_unreasonable_and_negative_price_filters_are_ignored_and_not_reflected(self):
        make_product("Visible fern")
        for index in range(12):
            make_product(f"Visible pagination plant {index}")

        for value in ("9" * 300, "-1"):
            with self.subTest(value=value[:10]):
                response = self.client.get(reverse("store:products"), {"max_price": value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["total_count"], 13)
                self.assertEqual(response.context["max_price"], "")
                self.assertContains(response, 'href="?page=2"')
                self.assertNotContains(response, "999999999999999999999999999999")

    def test_inactive_product_detail_returns_404(self):
        product, _ = make_product(active=False)
        self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 404)


class CategoryHierarchyTests(TestCase):
    def test_long_parent_cycle_is_rejected(self):
        categories = [Category.objects.create(name=f"Hierarchy {index}") for index in range(22)]
        for index in range(1, len(categories) - 1):
            categories[index].parent = categories[index + 1]
            categories[index].save(update_fields=["parent"])
        categories[-1].parent = categories[0]
        categories[-1].save(update_fields=["parent"])
        categories[0].parent = categories[1]
        categories[0].save(update_fields=["parent"])

        self.assertSetEqual(
            set(categories[0].descendant_ids()),
            {category.pk for category in categories},
        )

        with self.assertRaises(ValidationError):
            categories[0].full_clean()


class CartTests(TestCase):
    def setUp(self):
        self.product, self.variant = make_product(stock=3)

    def test_cannot_add_more_than_stock(self):
        response = self.client.post(reverse("store:cart_add"), {"variant_id": self.variant.pk, "quantity": 5}, **JSON)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_cart_totals_come_from_server_prices(self):
        self.client.post(reverse("store:cart_add"), {"variant_id": self.variant.pk, "quantity": 2}, **JSON)
        data = self.client.get(reverse("store:cart_api")).json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["subtotal"], "₹998")

    def test_header_badge_matches_cart_page_and_api(self):
        self.client.post(reverse("store:cart_add"), {"variant_id": self.variant.pk, "quantity": 2}, **JSON)

        home = self.client.get(reverse("store:home"))
        cart = self.client.get(reverse("store:cart"))
        api = self.client.get(reverse("store:cart_api")).json()

        self.assertEqual(home.context["cart_count"], 2)
        self.assertEqual(cart.context["summary"]["count"], 2)
        self.assertEqual(api["count"], 2)

    def test_quantity_zero_removes_line(self):
        self.client.post(reverse("store:cart_add"), {"variant_id": self.variant.pk, "quantity": 1}, **JSON)
        item = self.client.get(reverse("store:cart_api")).json()["lines"][0]
        self.client.post(reverse("store:cart_update", args=[item["id"]]), {"quantity": 0}, **JSON)
        self.assertEqual(self.client.get(reverse("store:cart_api")).json()["count"], 0)


class CheckoutTests(TestCase):
    def setUp(self):
        self.product, self.variant = make_product(stock=3)
        site = SiteSettings.load()
        site.cod_enabled = True
        site.save()
        self.client.post(reverse("store:cart_add"), {"variant_id": self.variant.pk, "quantity": 2})
        self.client.get(reverse("store:checkout"))
        self.token = self.client.session["checkout_token"]

    def form_data(self, **overrides):
        data = {"full_name": "Test Customer", "phone": "9876543210", "line1": "1 Garden Road", "city": "Kolkata",
                "state": "West Bengal", "pincode": "700001", "payment_method": "cod",
                "checkout_token": self.token}
        data.update(overrides)
        return data

    def test_order_decrements_stock_and_snapshots_items(self):
        self.client.post(reverse("store:checkout"), self.form_data())
        order = Order.objects.get()
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 1)
        self.assertEqual(order.total, Decimal("998.00"))
        self.assertEqual(order.items.get().product_name, "Snake Plant")
        self.assertTrue(order.events.exists())

    def test_duplicate_submission_creates_one_order(self):
        self.client.post(reverse("store:checkout"), self.form_data())
        self.client.post(reverse("store:checkout"), self.form_data())
        self.assertEqual(Order.objects.count(), 1)

    def test_mail_backend_failure_does_not_break_order_placement(self):
        with mock.patch(
            "store.services.send_mail",
            side_effect=RuntimeError("mail backend unavailable"),
        ):
            with self.assertLogs("store.services", level="ERROR"):
                response = self.client.post(
                    reverse("store:checkout"),
                    self.form_data(email="customer@example.com"),
                )

        order = Order.objects.get()
        self.assertRedirects(
            response,
            reverse("store:order_success", args=[order.number]),
            fetch_redirect_response=False,
        )

    def test_concurrent_checkout_submission_reuses_order(self):
        def create_racing_order(**kwargs):
            Order.objects.create(
                user=None,
                idempotency_key=kwargs["idempotency_key"],
                phone=kwargs["data"]["phone"],
                payment_method=kwargs["payment_method"],
                subtotal=Decimal("998.00"),
                shipping_fee=Decimal("0.00"),
                total=Decimal("998.00"),
                shipping_address={"full_name": "Test Customer"},
            )
            raise IntegrityError("idempotency key already used")

        self.client.raise_request_exception = False
        with mock.patch("store.commerce.create_order", side_effect=create_racing_order):
            response = self.client.post(reverse("store:checkout"), self.form_data())

        order = Order.objects.get()
        self.assertRedirects(
            response,
            reverse("store:order_success", args=[order.number]),
            fetch_redirect_response=False,
        )
        self.assertIn(order.number, self.client.session["recent_orders"])

    def test_stock_dropped_before_checkout_blocks_order(self):
        StockMovement.objects.create(variant=self.variant, change=-2, reason=StockMovement.Reason.ADJUSTMENT)
        self.client.post(reverse("store:checkout"), self.form_data())
        self.assertEqual(Order.objects.count(), 0)

    def test_stock_movement_cannot_go_negative(self):
        with self.assertRaises(Exception):
            StockMovement.objects.create(variant=self.variant, change=-99, reason=StockMovement.Reason.ADJUSTMENT)


class AccessControlTests(TestCase):
    def test_wishlist_requires_login(self):
        response = self.client.get(reverse("store:wishlist"))
        self.assertEqual(response.status_code, 302)

    def test_customer_cannot_open_another_customers_order(self):
        owner = User.objects.create_user(username="owner", email="owner@example.com", password="Str0ng-pass-123")
        other = User.objects.create_user(username="other", email="other@example.com", password="Str0ng-pass-123")
        order = Order.objects.create(user=owner, phone="9876543210", subtotal=Decimal("10"),
                                     shipping_fee=Decimal("0"), total=Decimal("10"), shipping_address={})
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("accounts:order_detail", args=[order.number])).status_code, 404)


class WishlistViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="wishlist-owner",
            email="wishlist-owner@example.com",
            password="Safe-pass-123",
        )
        self.client.force_login(self.user)
        self.product, _ = make_product("Wishlist Plant")

    def test_add_view_and_remove_wishlist_item(self):
        toggle_url = reverse("store:wishlist_toggle", args=[self.product.pk])
        added = self.client.post(toggle_url, **JSON).json()
        listing = self.client.get(reverse("store:wishlist"))

        self.assertTrue(added["in_wishlist"])
        self.assertContains(listing, self.product.name)
        self.assertEqual(self.product.wishlisted_by.count(), 1)

        removed = self.client.post(toggle_url, **JSON).json()

        self.assertFalse(removed["in_wishlist"])
        self.assertNotContains(self.client.get(reverse("store:wishlist")), self.product.name)
        self.assertEqual(self.product.wishlisted_by.count(), 0)

    def test_customer_cannot_edit_another_customers_address(self):
        owner = User.objects.create_user(username="owner2", email="owner2@example.com", password="Str0ng-pass-123")
        other = User.objects.create_user(username="other2", email="other2@example.com", password="Str0ng-pass-123")
        address = Address.objects.create(user=owner, full_name="Owner", phone="9876543210", line1="x", city="c",
                                         state="s", pincode="700001")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("accounts:address_edit", args=[address.pk])).status_code, 404)
