"""Coupon validation and checkout totals. Run: python manage.py test store"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Category, Coupon, Order, Product, ProductVariant, SiteSettings, StockMovement
from .services import get_cart  # noqa: F401
from .tests import make_product

CHECKOUT = {"full_name": "Rita Das", "phone": "9876543210", "line1": "1 Park St", "city": "Kolkata",
            "state": "West Bengal", "pincode": "700016", "payment_method": "cod"}


class CouponCheckoutTests(TestCase):
    def setUp(self):
        site = SiteSettings.load()
        site.cod_enabled = True
        site.shipping_fee = Decimal("50.00")
        site.save()
        self.product, self.variant = make_product("Rose", price="500.00", stock=10)
        self.client.post(reverse("store:cart_add"), {"variant_id": self.variant.pk, "quantity": 2})  # subtotal 1000

    def coupon(self, **kw):
        defaults = dict(code="SAVE10", discount_type="percent", value=Decimal("10"))
        defaults.update(kw)
        return Coupon.objects.create(**defaults)

    def apply(self, code):
        return self.client.post(reverse("store:coupon_apply"), {"coupon_code": code}, follow=True)

    def place(self):
        page = self.client.get(reverse("store:checkout"))
        token = page.context["checkout_token"]
        return self.client.post(reverse("store:checkout"), {**CHECKOUT, "checkout_token": token})

    def test_percent_discount_applied_server_side(self):
        self.coupon()
        self.apply("save10")  # case-insensitive
        self.place()
        order = Order.objects.get()
        self.assertEqual(order.discount_total, Decimal("100.00"))
        self.assertEqual(order.total, Decimal("950.00"))  # 1000 - 100 + 50 shipping
        self.assertEqual(order.coupon_code, "SAVE10")
        self.assertEqual(order.coupon_redemption.discount_amount, Decimal("100.00"))

    def test_fixed_discount_never_exceeds_subtotal(self):
        self.coupon(code="BIG", discount_type="fixed", value=Decimal("5000"))
        self.apply("BIG")
        self.place()
        order = Order.objects.get()
        self.assertEqual(order.discount_total, Decimal("1000.00"))
        self.assertEqual(order.total, Decimal("50.00"))

    def test_invalid_expired_disabled_not_started_are_rejected(self):
        now = timezone.now()
        self.coupon(code="OLD", ends_at=now - timedelta(days=1))
        self.coupon(code="OFF", is_active=False)
        self.coupon(code="LATER", starts_at=now + timedelta(days=1))
        for index, code in enumerate(("NOPE", "OLD", "OFF", "LATER")):
            if index:
                self.client.post(reverse("store:cart_add"), {
                    "variant_id": self.variant.pk, "quantity": 2
                })
            self.apply(code)
            self.place()
        self.assertFalse(Order.objects.filter(discount_total__gt=0).exists())

    def test_minimum_order_value(self):
        self.coupon(code="MIN", min_order_value=Decimal("5000"))
        self.apply("MIN")
        self.place()
        self.assertEqual(Order.objects.get().discount_total, Decimal("0.00"))

    def test_usage_limit_and_cancellation_frees_a_use(self):
        coupon = self.coupon(code="ONCE", usage_limit=1)
        self.apply("ONCE")
        self.place()
        self.assertEqual(coupon.times_used, 1)
        self.client.post(reverse("store:cart_add"), {"variant_id": self.variant.pk, "quantity": 1})
        self.apply("ONCE")
        self.place()
        self.assertEqual(Order.objects.filter(coupon_code="ONCE").count(), 1)  # second use refused
        from .services import transition_order
        transition_order(Order.objects.get(coupon_code="ONCE"), Order.Status.CANCELLED)
        self.assertEqual(coupon.times_used, 0)

    def test_product_restriction(self):
        other, _ = make_product("Fern", price="100.00")
        coupon = self.coupon(code="FERNONLY")
        coupon.products.add(other)
        self.apply("FERNONLY")
        self.place()
        self.assertEqual(Order.objects.get().discount_total, Decimal("0.00"))  # cart has only Rose

    def test_oversized_coupon_code_is_not_truncated_to_a_valid_code(self):
        code = "A" * 40
        self.coupon(code=code)
        self.apply(code + "EXTRA")
        self.assertNotIn("coupon_code", self.client.session)

    def test_tampered_post_fields_do_not_change_discount(self):
        self.coupon()
        self.apply("SAVE10")
        page = self.client.get(reverse("store:checkout"))
        self.client.post(reverse("store:checkout"), {**CHECKOUT, "checkout_token": page.context["checkout_token"],
                                                      "discount_total": "999", "coupon_code": "FREE", "total": "1"})
        order = Order.objects.get()
        self.assertEqual(order.discount_total, Decimal("100.00"))
        self.assertEqual(order.total, Decimal("950.00"))

    def test_coupon_validation_rules(self):
        with self.assertRaises(ValidationError):
            Coupon(code="X", discount_type="percent", value=Decimal("150")).full_clean()
