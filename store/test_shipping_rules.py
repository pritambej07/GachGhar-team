from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Coupon, Order, SiteSettings
from .services import shipping_fee_for
from .tests import make_product


class DeliveryChargeRulesTests(TestCase):
    def setUp(self):
        self.site = SiteSettings.load()
        self.site.shipping_fee = Decimal("60.00")
        self.site.free_shipping_threshold = Decimal("999.00")
        self.site.save()

    def test_flat_delivery_fee_below_threshold(self):
        self.assertEqual(shipping_fee_for(Decimal("500.00")), Decimal("60.00"))

    def test_free_delivery_at_threshold(self):
        self.assertEqual(shipping_fee_for(Decimal("999.00")), Decimal("0.00"))

    def test_free_delivery_above_threshold(self):
        self.assertEqual(shipping_fee_for(Decimal("1200.00")), Decimal("0.00"))

    def test_empty_cart_has_no_delivery_fee(self):
        self.assertEqual(shipping_fee_for(Decimal("0.00")), Decimal("0.00"))

    def test_blank_threshold_disables_free_delivery(self):
        self.site.free_shipping_threshold = None
        self.site.save()
        self.assertEqual(shipping_fee_for(Decimal("5000.00")), Decimal("60.00"))

    def test_negative_free_shipping_threshold_is_rejected(self):
        self.site.free_shipping_threshold = Decimal("-1.00")
        with self.assertRaises(ValidationError):
            self.site.full_clean()

    def test_negative_flat_delivery_fee_is_rejected(self):
        self.site.shipping_fee = Decimal("-0.01")
        with self.assertRaises(ValidationError):
            self.site.full_clean()

    def test_zero_flat_delivery_fee_is_valid(self):
        self.site.shipping_fee = Decimal("0.00")
        self.site.full_clean()
        self.site.save()
        self.assertEqual(shipping_fee_for(Decimal("500.00")), Decimal("0.00"))

    def test_zero_free_shipping_threshold_is_valid_and_applies_to_positive_subtotals(self):
        self.site.free_shipping_threshold = Decimal("0.00")
        self.site.full_clean()
        self.site.save()
        self.assertEqual(shipping_fee_for(Decimal("0.01")), Decimal("0.00"))


class DiscountAndDeliveryThresholdTests(TestCase):
    def test_coupon_does_not_remove_free_shipping_eligibility(self):
        site = SiteSettings.load()
        site.cod_enabled = True
        site.shipping_fee = Decimal("60.00")
        site.free_shipping_threshold = Decimal("500.00")
        site.save()
        _, variant = make_product("Threshold Plant", price="500.00", stock=5)
        self.client.post(reverse("store:cart_add"), {"variant_id": variant.pk, "quantity": 1})
        Coupon.objects.create(code="TAKE10", discount_type="percent", value=Decimal("10"))
        self.client.post(reverse("store:coupon_apply"), {"coupon_code": "TAKE10"})
        page = self.client.get(reverse("store:checkout"))
        self.assertEqual(page.context["totals"]["shipping"], Decimal("0.00"))
        self.client.post(reverse("store:checkout"), {
            "full_name": "Asha Roy", "phone": "9876543210", "line1": "1 Green Road",
            "city": "Kolkata", "state": "West Bengal", "pincode": "700001",
            "payment_method": "cod", "checkout_token": page.context["checkout_token"],
        })
        order = Order.objects.get()
        self.assertEqual(order.shipping_fee, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("450.00"))
