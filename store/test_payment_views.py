import hashlib
import hmac
import json
import re
import secrets
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.template.loader import render_to_string
from django.urls import reverse

from .models import (
    Category,
    Cart,
    CartItem,
    Order,
    Product,
    ProductVariant,
    RazorpayWebhookEvent,
    SiteSettings,
    StockMovement,
)


User = get_user_model()


@override_settings(RAZORPAY_KEY_ID="rzp_test_session", RAZORPAY_KEY_SECRET="test-secret")
class GuestCheckoutPaymentSessionTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Payment Session Plants")
        product = Product.objects.create(name="Session Plant", category=category)
        self.variant = ProductVariant.objects.create(
            product=product,
            name="Standard",
            sku="PAYMENT-SESSION-PLANT",
            price=Decimal("250.00"),
        )
        StockMovement.objects.create(
            variant=self.variant,
            change=2,
            reason=StockMovement.Reason.RESTOCK,
        )
        site = SiteSettings.load()
        site.cod_enabled = True
        site.save()
        self.client.post(
            reverse("store:cart_add"),
            {"variant_id": self.variant.pk, "quantity": 1},
        )
        self.client.get(reverse("store:checkout"))
        self.checkout_token = self.client.session["checkout_token"]

    def checkout_data(self):
        return {
            "full_name": "Guest Customer",
            "email": "guest@example.com",
            "phone": "9876543210",
            "line1": "1 Garden Road",
            "city": "Kolkata",
            "state": "West Bengal",
            "pincode": "700001",
            "payment_method": "razorpay",
            "checkout_token": self.checkout_token,
        }

    def browser_checkout(self, *, username=None, payment_method="cod"):
        client = Client(enforce_csrf_checks=True)
        if username:
            user = User.objects.create_user(
                username=username,
                email=f"{username}@example.com",
                password="Safe-pass-123",
            )
            client.force_login(user)
            cart = Cart.objects.create(user=user)
        else:
            user = None
            guest_token = secrets.token_urlsafe(32)
            cart = Cart.objects.create(guest_token=guest_token)
            session = client.session
            session["guest_cart_token"] = guest_token
            session.save()
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)

        checkout_page = client.get(reverse("store:checkout"))
        self.assertEqual(checkout_page.status_code, 200)
        html = checkout_page.content.decode()
        for field_name in (
            "csrfmiddlewaretoken", "checkout_token", "full_name", "email",
            "phone", "line1", "line2", "city", "state", "pincode", "payment_method",
        ):
            self.assertIn(f'name="{field_name}"', html)
        csrf_match = re.search(
            r'name="csrfmiddlewaretoken"\s+value="([^"]+)"',
            html,
        )
        self.assertIsNotNone(csrf_match)
        choices = dict(checkout_page.context["form"].fields["payment_method"].choices)
        self.assertIn("cod", choices)
        self.assertIn("razorpay", choices)

        data = {
            "csrfmiddlewaretoken": csrf_match.group(1),
            "checkout_token": checkout_page.context["checkout_token"],
            "full_name": "Browser Customer",
            "email": "browser@example.com",
            "phone": "9876543210",
            "line1": "1 Garden Road",
            "line2": "",
            "city": "Kolkata",
            "state": "West Bengal",
            "pincode": "700001",
            "payment_method": payment_method,
        }
        return client, user, data

    def assert_browser_checkout(self, *, username, payment_method):
        client, user, data = self.browser_checkout(
            username=username,
            payment_method=payment_method,
        )
        if payment_method == "razorpay":
            gateway = mock.patch(
                "store.commerce.create_gateway_order",
                return_value={"id": f"order_{username or 'guest'}_browser"},
            )
        else:
            gateway = mock.patch("store.commerce.create_gateway_order")

        with gateway as create_gateway_order:
            response = client.post(reverse("store:checkout"), data, follow=True)

        order_query = Order.objects.filter(user=user) if user else Order.objects.filter(user__isnull=True)
        order = order_query.get()
        self.assertEqual(response.status_code, 200)
        target = "payment_page" if payment_method == "razorpay" else "order_success"
        self.assertEqual(response.request["PATH_INFO"], reverse(f"store:{target}", args=[order.number]))
        self.assertEqual(order.payment_method, payment_method)
        if payment_method == "razorpay":
            order.refresh_from_db()
            self.assertTrue(order.razorpay_order_id)
            create_gateway_order.assert_called_once_with(order)
        else:
            self.assertEqual(order.razorpay_order_id, "")
            create_gateway_order.assert_not_called()
        return order

    def test_browser_guest_cod_checkout(self):
        self.assert_browser_checkout(username=None, payment_method="cod")

    def test_browser_guest_razorpay_checkout(self):
        self.assert_browser_checkout(username=None, payment_method="razorpay")

    def test_browser_logged_in_cod_checkout(self):
        self.assert_browser_checkout(username="browser-cod-owner", payment_method="cod")

    def test_browser_logged_in_razorpay_checkout(self):
        self.assert_browser_checkout(username="browser-pay-owner", payment_method="razorpay")

    def test_invalid_browser_checkout_is_validation_error_not_404(self):
        cases = (
            (None, "cod"),
            (None, "razorpay"),
            ("invalid-checkout-cod", "cod"),
            ("invalid-checkout-razorpay", "razorpay"),
        )
        for username, payment_method in cases:
            with self.subTest(username=username, payment_method=payment_method):
                client, _, data = self.browser_checkout(
                    username=username,
                    payment_method=payment_method,
                )
                data["phone"] = "not-a-phone"
                response = client.post(reverse("store:checkout"), data)

                self.assertEqual(response.status_code, 200)
                self.assertIn("phone", response.context["form"].errors)
                self.assertFalse(Order.objects.exists())

    def test_cross_owner_retry_is_rejected_without_404_for_both_payment_choices(self):
        other_user = User.objects.create_user(
            username="different-checkout-owner",
            email="different-checkout-owner@example.com",
            password="Safe-pass-123",
        )
        for payment_method in ("cod", "razorpay"):
            with self.subTest(payment_method=payment_method):
                client, _, data = self.browser_checkout(
                    username=f"retry-{payment_method}-user",
                    payment_method=payment_method,
                )
                order = Order.objects.create(
                    user=other_user,
                    phone="9876543210",
                    idempotency_key=data["checkout_token"],
                    payment_method=payment_method,
                    subtotal=Decimal("250.00"),
                    shipping_fee=Decimal("0.00"),
                    total=Decimal("250.00"),
                    shipping_address={"full_name": "Other Customer"},
                )
                order_count = Order.objects.count()

                response = client.post(reverse("store:checkout"), data, follow=True)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "checkout session has expired")
                self.assertEqual(Order.objects.count(), order_count)
                order.refresh_from_db()
                self.assertEqual(order.user_id, other_user.pk)

    def test_guest_order_creation_persists_session_and_opens_checkout(self):
        with mock.patch(
            "store.commerce.create_gateway_order",
            return_value={"id": "order_guest_session"},
        ):
            response = self.client.post(
                reverse("store:checkout"),
                self.checkout_data(),
                follow=True,
            )

        order = Order.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("store:payment_page", args=[order.number]))
        self.assertIn(order.number, self.client.session["recent_orders"])
        self.assertEqual(order.user_id, None)
        order.refresh_from_db()
        self.assertEqual(order.razorpay_order_id, "order_guest_session")

    def test_logged_in_customer_checkout_post_opens_payment_page(self):
        user = User.objects.create_user(
            username="payment-session-owner",
            email="payment-session-owner@example.com",
            password="Safe-pass-123",
        )
        client = self.client_class()
        client.force_login(user)
        client.post(
            reverse("store:cart_add"),
            {"variant_id": self.variant.pk, "quantity": 1},
        )
        client.get(reverse("store:checkout"))
        data = self.checkout_data()
        data["checkout_token"] = client.session["checkout_token"]

        with mock.patch(
            "store.commerce.create_gateway_order",
            return_value={"id": "order_member_session"},
        ):
            response = client.post(reverse("store:checkout"), data, follow=True)

        order = Order.objects.get(user=user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("store:payment_page", args=[order.number]))
        self.assertEqual(order.payment_method, "razorpay")

    def test_idempotent_guest_retry_restores_session_ownership(self):
        order = Order.objects.create(
            email="guest@example.com",
            phone="9876543210",
            idempotency_key=self.checkout_token,
            payment_method="razorpay",
            subtotal=Decimal("250.00"),
            shipping_fee=Decimal("0.00"),
            total=Decimal("250.00"),
            shipping_address={"full_name": "Guest Customer"},
        )
        with mock.patch(
            "store.commerce.create_gateway_order",
            return_value={"id": "order_guest_retry"},
        ):
            response = self.client.post(
                reverse("store:checkout"),
                self.checkout_data(),
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("store:payment_page", args=[order.number]))
        self.assertIn(order.number, self.client.session["recent_orders"])
        self.assertEqual(Order.objects.count(), 1)

    def test_idempotent_guest_retry_survives_rotated_checkout_session_token(self):
        previous_token = "previous-session-checkout-token"
        order = Order.objects.create(
            email="guest@example.com",
            phone="9876543210",
            idempotency_key=previous_token,
            payment_method="razorpay",
            subtotal=Decimal("250.00"),
            shipping_fee=Decimal("0.00"),
            total=Decimal("250.00"),
            shipping_address={"full_name": "Guest Customer"},
        )
        data = self.checkout_data()
        data["checkout_token"] = previous_token

        with mock.patch(
            "store.commerce.create_gateway_order",
            return_value={"id": "order_guest_retry"},
        ):
            response = self.client.post(
                reverse("store:checkout"),
                data,
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("store:payment_page", args=[order.number]))
        self.assertIn(order.number, self.client.session["recent_orders"])
        self.assertEqual(Order.objects.count(), 1)

    def test_original_checkout_token_recovers_direct_payment_page_access(self):
        order = Order.objects.create(
            email="guest@example.com",
            phone="9876543210",
            idempotency_key=self.checkout_token,
            payment_method="razorpay",
            subtotal=Decimal("250.00"),
            shipping_fee=Decimal("0.00"),
            total=Decimal("250.00"),
            shipping_address={"full_name": "Guest Customer"},
        )
        with mock.patch(
            "store.commerce.create_gateway_order",
            return_value={"id": "order_guest_recovered"},
        ):
            response = self.client.get(reverse("store:payment_page", args=[order.number]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(order.number, self.client.session["recent_orders"])
        order.refresh_from_db()
        self.assertEqual(order.razorpay_order_id, "order_guest_recovered")

    def test_different_browser_session_cannot_access_guest_payment(self):
        order = Order.objects.create(
            phone="9876543210",
            payment_method="razorpay",
            subtotal=Decimal("250.00"),
            shipping_fee=Decimal("0.00"),
            total=Decimal("250.00"),
            shipping_address={},
        )
        response = self.client_class().get(reverse("store:payment_page", args=[order.number]))
        self.assertEqual(response.status_code, 404)


class PaymentRecoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="payment-owner",
            email="payment-owner@example.com",
            password="Safe-pass-123",
        )
        self.client.force_login(self.user)
        self.order = Order.objects.create(
            user=self.user,
            email=self.user.email,
            phone="9876543210",
            payment_method="razorpay",
            subtotal=Decimal("500.00"),
            shipping_fee=Decimal("50.00"),
            total=Decimal("550.00"),
            shipping_address={"full_name": "Payment Owner"},
        )
        self.payment_url = reverse("store:payment_page", args=[self.order.number])
        self.success_url = reverse("store:order_success", args=[self.order.number])

    def test_gateway_order_failure_leaves_a_retry_action_on_order_page(self):
        with mock.patch("store.commerce.create_gateway_order", side_effect=RuntimeError("gateway unavailable")):
            with self.assertLogs("store.commerce", level="ERROR") as log:
                response = self.client.get(self.payment_url)

        self.assertRedirects(response, self.success_url)
        self.assertIn(self.order.number, log.output[0])
        self.assertContains(self.client.get(self.success_url), "Retry payment")

    def test_customer_can_retry_and_gateway_order_is_saved(self):
        with mock.patch("store.commerce.create_gateway_order", return_value={"id": "order_retry_123"}):
            response = self.client.get(self.payment_url)

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.razorpay_order_id, "order_retry_123")
        self.assertContains(response, "Pay")

    def test_payment_response_csp_allows_official_razorpay_checkout_frame(self):
        with mock.patch("store.commerce.create_gateway_order", return_value={"id": "order_csp_123"}):
            response = self.client.get(self.payment_url)

        policy = response["Content-Security-Policy"]
        self.assertIn(
            "frame-src https://checkout.razorpay.com https://api.razorpay.com",
            policy,
        )
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertContains(response, "https://checkout.razorpay.com/v1/checkout.js")
        self.assertNotContains(response, "<iframe")

    def test_refunded_order_cannot_start_another_payment(self):
        self.order.payment_status = Order.PaymentStatus.REFUNDED
        self.order.save(update_fields=["payment_status", "updated_at"])

        with mock.patch("store.commerce.create_gateway_order") as create_order:
            response = self.client.get(self.payment_url)

        self.assertRedirects(response, self.success_url)
        create_order.assert_not_called()
        self.assertNotContains(self.client.get(self.success_url), "Retry payment")

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test-secret")
    def test_signed_webhook_with_non_object_json_returns_bad_request(self):
        body = b"[]"
        signature = hmac.new(
            b"webhook-test-secret",
            body,
            hashlib.sha256,
        ).hexdigest()

        response = self.client.post(
            reverse("store:razorpay_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 400)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test-secret")
    def test_webhooks_reject_amounts_outside_order_field_range(self):
        events = (
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_huge_amount",
                            "order_id": "order_huge_amount",
                            "amount": "9" * 100,
                            "currency": "INR",
                        }
                    }
                },
            },
            {
                "event": "refund.processed",
                "payload": {
                    "refund": {
                        "entity": {
                            "id": "rfnd_huge_amount",
                            "payment_id": "pay_huge_amount",
                            "amount": "9" * 100,
                            "currency": "INR",
                            "status": "processed",
                        }
                    }
                },
            },
        )

        for index, payload in enumerate(events):
            with self.subTest(event=payload["event"]):
                body = json.dumps(payload).encode()
                signature = hmac.new(b"webhook-test-secret", body, hashlib.sha256).hexdigest()
                response = self.client.post(
                    reverse("store:razorpay_webhook"),
                    data=body,
                    content_type="application/json",
                    HTTP_X_RAZORPAY_SIGNATURE=signature,
                    HTTP_X_RAZORPAY_EVENT_ID=f"evt_huge_amount_{index}",
                )
                self.assertEqual(response.status_code, 400)

        self.assertFalse(RazorpayWebhookEvent.objects.exists())

    def test_owner_payment_is_marked_paid_only_after_gateway_capture_verification(self):
        self.order.razorpay_order_id = "order_payment_123"
        self.order.save(update_fields=["razorpay_order_id", "updated_at"])
        client = mock.Mock()
        client.payment.fetch.return_value = {
            "status": "captured",
            "amount": 55000,
            "currency": "INR",
            "order_id": self.order.razorpay_order_id,
        }
        payload = {
            "razorpay_order_id": self.order.razorpay_order_id,
            "razorpay_payment_id": "pay_payment_123",
            "razorpay_signature": "valid-signature",
        }

        with mock.patch("store.payment_views.verify_checkout_signature") as verify:
            with mock.patch("store.payment_views.get_client", return_value=client):
                response = self.client.post(reverse("store:verify_payment"), payload)

        self.assertRedirects(response, self.success_url)
        verify.assert_called_once_with(
            self.order.razorpay_order_id,
            "pay_payment_123",
            "valid-signature",
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.razorpay_payment_id, "pay_payment_123")
        self.assertIsNotNone(self.order.payment_verified_at)

    def test_notification_failure_does_not_report_verified_payment_as_failed(self):
        self.order.razorpay_order_id = "order_notification_failure"
        self.order.save(update_fields=["razorpay_order_id", "updated_at"])
        client = mock.Mock()
        client.payment.fetch.return_value = {
            "status": "captured",
            "amount": 55000,
            "currency": "INR",
            "order_id": self.order.razorpay_order_id,
        }

        with self.assertLogs("store.payment_views", level="ERROR"):
            with mock.patch("store.payment_views.verify_checkout_signature"):
                with mock.patch("store.payment_views.get_client", return_value=client):
                    with mock.patch(
                        "store.payment_views.send_order_notification",
                        side_effect=RuntimeError("mail backend unavailable"),
                    ):
                        response = self.client.post(reverse("store:verify_payment"), {
                            "razorpay_order_id": self.order.razorpay_order_id,
                            "razorpay_payment_id": "pay_notification_failure",
                            "razorpay_signature": "valid-signature",
                        })

        self.assertRedirects(response, self.success_url)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_wrong_amount_payment_stays_pending(self):
        self.order.razorpay_order_id = "order_payment_456"
        self.order.save(update_fields=["razorpay_order_id", "updated_at"])
        client = mock.Mock()
        client.payment.fetch.return_value = {
            "status": "captured",
            "amount": 1,
            "currency": "INR",
            "order_id": self.order.razorpay_order_id,
        }

        with mock.patch("store.payment_views.verify_checkout_signature"):
            with mock.patch("store.payment_views.get_client", return_value=client):
                response = self.client.post(reverse("store:verify_payment"), {
                    "razorpay_order_id": self.order.razorpay_order_id,
                    "razorpay_payment_id": "pay_mismatch",
                    "razorpay_signature": "valid-signature",
                })

        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    def test_late_capture_callback_does_not_reverse_refund_status(self):
        self.order.razorpay_order_id = "order_refunded_123"
        self.order.payment_status = Order.PaymentStatus.REFUNDED
        self.order.save(update_fields=["razorpay_order_id", "payment_status", "updated_at"])
        client = mock.Mock()
        client.payment.fetch.return_value = {
            "status": "captured",
            "amount": 55000,
            "currency": "INR",
            "order_id": self.order.razorpay_order_id,
        }

        with mock.patch("store.payment_views.verify_checkout_signature"):
            with mock.patch("store.payment_views.get_client", return_value=client):
                response = self.client.post(reverse("store:verify_payment"), {
                    "razorpay_order_id": self.order.razorpay_order_id,
                    "razorpay_payment_id": "pay_late_capture",
                    "razorpay_signature": "valid-signature",
                })

        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUNDED)

    def test_late_capture_callback_does_not_pay_cancelled_order(self):
        self.order.razorpay_order_id = "order_cancelled_123"
        self.order.status = Order.Status.CANCELLED
        self.order.save(update_fields=["razorpay_order_id", "status", "updated_at"])
        client = mock.Mock()
        client.payment.fetch.return_value = {
            "status": "captured",
            "amount": 55000,
            "currency": "INR",
            "order_id": self.order.razorpay_order_id,
        }

        with self.assertLogs("store.payment_views", level="ERROR"):
            with mock.patch("store.payment_views.verify_checkout_signature"):
                with mock.patch("store.payment_views.get_client", return_value=client):
                    response = self.client.post(reverse("store:verify_payment"), {
                        "razorpay_order_id": self.order.razorpay_order_id,
                        "razorpay_payment_id": "pay_cancelled_capture",
                        "razorpay_signature": "valid-signature",
                    })

        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test-secret")
    def test_captured_webhook_is_idempotent(self):
        self.order.razorpay_order_id = "order_webhook_123"
        self.order.save(update_fields=["razorpay_order_id", "updated_at"])
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook_123",
                        "order_id": self.order.razorpay_order_id,
                        "amount": 55000,
                        "currency": "INR",
                    }
                }
            },
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"webhook-test-secret", body, hashlib.sha256).hexdigest()

        def send_webhook():
            return self.client.post(
                reverse("store:razorpay_webhook"),
                data=body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=signature,
                HTTP_X_RAZORPAY_EVENT_ID="evt_payment_123",
            )

        response = send_webhook()
        duplicate = send_webhook()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(duplicate.content, b"Duplicate OK")
        self.assertEqual(RazorpayWebhookEvent.objects.count(), 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.razorpay_payment_id, "pay_webhook_123")

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test-secret")
    def test_processed_full_refund_webhook_marks_order_refunded(self):
        self.order.payment_status = Order.PaymentStatus.PAID
        self.order.razorpay_payment_id = "pay_refund_123"
        self.order.save(update_fields=["payment_status", "razorpay_payment_id", "updated_at"])
        payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_full_123",
                        "payment_id": "pay_refund_123",
                        "amount": 55000,
                        "currency": "INR",
                        "status": "processed",
                    }
                }
            },
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"webhook-test-secret", body, hashlib.sha256).hexdigest()

        response = self.client.post(
            reverse("store:razorpay_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
            HTTP_X_RAZORPAY_EVENT_ID="evt_refund_full_123",
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUNDED)
        self.assertTrue(self.order.events.filter(note__contains="rfnd_full_123").exists())

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test-secret")
    def test_processed_partial_refund_does_not_mark_order_fully_refunded(self):
        self.order.payment_status = Order.PaymentStatus.PAID
        self.order.razorpay_payment_id = "pay_refund_partial"
        self.order.save(update_fields=["payment_status", "razorpay_payment_id", "updated_at"])
        payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_partial_123",
                        "payment_id": "pay_refund_partial",
                        "amount": 10000,
                        "currency": "INR",
                        "status": "processed",
                    }
                }
            },
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"webhook-test-secret", body, hashlib.sha256).hexdigest()

        response = self.client.post(
            reverse("store:razorpay_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
            HTTP_X_RAZORPAY_EVENT_ID="evt_refund_partial_123",
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertTrue(self.order.events.filter(note__contains="rfnd_partial_123").exists())

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test-secret")
    def test_multiple_processed_partial_refunds_mark_order_refunded_when_cumulative_total_matches(self):
        self.order.payment_status = Order.PaymentStatus.PAID
        self.order.razorpay_payment_id = "pay_refund_cumulative"
        self.order.save(update_fields=["payment_status", "razorpay_payment_id", "updated_at"])

        def send_refund(event_id, refund_id, amount):
            payload = {
                "event": "refund.processed",
                "payload": {
                    "refund": {
                        "entity": {
                            "id": refund_id,
                            "payment_id": "pay_refund_cumulative",
                            "amount": amount,
                            "currency": "INR",
                            "status": "processed",
                        }
                    }
                },
            }
            body = json.dumps(payload).encode()
            signature = hmac.new(b"webhook-test-secret", body, hashlib.sha256).hexdigest()
            return self.client.post(
                reverse("store:razorpay_webhook"),
                data=body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=signature,
                HTTP_X_RAZORPAY_EVENT_ID=event_id,
            )

        first = send_refund("evt_refund_part_1", "rfnd_part_1", 25000)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        second = send_refund("evt_refund_part_2", "rfnd_part_2", 30000)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUNDED)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test-secret")
    def test_refund_webhook_requires_processed_status(self):
        payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_pending_123",
                        "payment_id": "pay_refund_pending",
                        "amount": 55000,
                        "currency": "INR",
                        "status": "pending",
                    }
                }
            },
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"webhook-test-secret", body, hashlib.sha256).hexdigest()

        response = self.client.post(
            reverse("store:razorpay_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(RazorpayWebhookEvent.objects.exists())

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test-secret")
    def test_webhook_acknowledges_payment_when_notification_fails(self):
        self.order.razorpay_order_id = "order_webhook_notification_failure"
        self.order.save(update_fields=["razorpay_order_id", "updated_at"])
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook_notification_failure",
                        "order_id": self.order.razorpay_order_id,
                        "amount": 55000,
                        "currency": "INR",
                    }
                }
            },
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"webhook-test-secret", body, hashlib.sha256).hexdigest()

        with self.assertLogs("store.payment_views", level="ERROR"):
            with mock.patch(
                "store.payment_views.send_order_notification",
                side_effect=RuntimeError("mail backend unavailable"),
            ):
                response = self.client.post(
                    reverse("store:razorpay_webhook"),
                    data=body,
                    content_type="application/json",
                    HTTP_X_RAZORPAY_SIGNATURE=signature,
                    HTTP_X_RAZORPAY_EVENT_ID="evt_notification_failure",
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(RazorpayWebhookEvent.objects.get(event_id="evt_notification_failure").processed)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test-secret")
    def test_late_capture_webhook_does_not_reverse_refund_status(self):
        self.order.razorpay_order_id = "order_refunded_webhook"
        self.order.payment_status = Order.PaymentStatus.REFUNDED
        self.order.save(update_fields=["razorpay_order_id", "payment_status", "updated_at"])
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_late_webhook",
                        "order_id": self.order.razorpay_order_id,
                        "amount": 55000,
                        "currency": "INR",
                    }
                }
            },
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"webhook-test-secret", body, hashlib.sha256).hexdigest()

        with self.assertLogs("store.payment_views", level="WARNING"):
            response = self.client.post(
                reverse("store:razorpay_webhook"),
                data=body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=signature,
                HTTP_X_RAZORPAY_EVENT_ID="evt_late_webhook",
            )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUNDED)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test-secret")
    def test_late_capture_webhook_does_not_pay_cancelled_order(self):
        self.order.razorpay_order_id = "order_cancelled_webhook"
        self.order.status = Order.Status.CANCELLED
        self.order.save(update_fields=["razorpay_order_id", "status", "updated_at"])
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_cancelled_webhook",
                        "order_id": self.order.razorpay_order_id,
                        "amount": 55000,
                        "currency": "INR",
                    }
                }
            },
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"webhook-test-secret", body, hashlib.sha256).hexdigest()

        with self.assertLogs("store.payment_views", level="WARNING"):
            response = self.client.post(
                reverse("store:razorpay_webhook"),
                data=body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=signature,
                HTTP_X_RAZORPAY_EVENT_ID="evt_cancelled_webhook",
            )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    def test_legacy_payment_template_uses_current_route_and_context(self):
        rendered = render_to_string(
            "payments/checkout.html",
            {
                "order": SimpleNamespace(
                    number="GGTEST123",
                    total=Decimal("550.00"),
                    razorpay_order_id="order_template_123",
                ),
                "razorpay_key": "test-key",
                "amount_paise": 55000,
            },
        )

        self.assertIn(reverse("store:verify_payment"), rendered)
        self.assertIn("order_template_123", rendered)
        self.assertIn("55000", rendered)
