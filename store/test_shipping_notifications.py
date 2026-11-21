from datetime import date
from decimal import Decimal
from smtplib import SMTPException
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import (
    Category,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    Shipment,
    StockMovement,
)
from .services import record_payment, record_shipment_update, send_order_notification, transition_order


User = get_user_model()


class ShipmentAndNotificationTests(TestCase):
    def make_order(self, **kwargs):
        defaults = {
            "email": "customer@example.com",
            "phone": "9876543210",
            "subtotal": Decimal("500.00"),
            "shipping_fee": Decimal("50.00"),
            "total": Decimal("550.00"),
            "shipping_address": {"full_name": "Test Customer", "city": "Kolkata"},
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def test_order_confirmation_sends_email(self):
        order = self.make_order()
        transition_order(order, Order.Status.CONFIRMED, note="Confirmed by staff.")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(order.number, mail.outbox[0].body)
        self.assertIn("confirmed", mail.outbox[0].subject.lower())

    def test_shipment_update_moves_confirmed_order_to_shipped_and_emails_tracking(self):
        order = self.make_order(status=Order.Status.CONFIRMED)
        shipment = Shipment.objects.create(
            order=order,
            carrier="Example Courier",
            tracking_number="GGTRACK123",
            tracking_url="https://courier.example/track/GGTRACK123",
            status=Shipment.Status.IN_TRANSIT,
        )
        record_shipment_update(shipment)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("GGTRACK123", mail.outbox[0].body)
        self.assertIn("https://courier.example/track/GGTRACK123", mail.outbox[0].body)

    def test_carrier_milestone_advances_placed_order_to_shipped(self):
        order = self.make_order()
        shipment = Shipment.objects.create(order=order, status=Shipment.Status.IN_TRANSIT)

        record_shipment_update(shipment)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)

    def test_unpaid_online_order_cannot_be_marked_shipped(self):
        order = self.make_order(
            status=Order.Status.CONFIRMED,
            payment_method="razorpay",
            payment_status=Order.PaymentStatus.PENDING,
        )

        with self.assertRaises(ValidationError):
            transition_order(order, Order.Status.SHIPPED)

    def test_unpaid_online_shipment_cannot_reach_carrier_milestone(self):
        order = self.make_order(
            payment_method="razorpay",
            payment_status=Order.PaymentStatus.PENDING,
        )
        shipment = Shipment(
            order=order,
            status=Shipment.Status.IN_TRANSIT,
        )

        with self.assertRaises(ValidationError):
            shipment.full_clean()

    def test_admin_rejects_carrier_milestone_for_unpaid_online_order(self):
        order = self.make_order(payment_method="razorpay")
        staff = User.objects.create_superuser(
            username="shipment-admin",
            email="shipment-admin@example.com",
            password="Safe-pass-123",
        )
        self.client.force_login(staff)

        response = self.client.post(reverse("admin:store_shipment_add"), {
            "order": order.pk,
            "carrier": "Example Courier",
            "tracking_number": "TRACK-123",
            "tracking_url": "",
            "status": Shipment.Status.IN_TRANSIT,
            "estimated_delivery": "",
            "shipped_at": "",
            "delivered_at": "",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verify the online payment before shipping this order.")
        self.assertFalse(Shipment.objects.filter(order=order).exists())

    def test_admin_cannot_rewind_shipment_status(self):
        order = self.make_order()
        shipment = Shipment.objects.create(
            order=order,
            carrier="Example Courier",
            tracking_number="TRACK-123",
            status=Shipment.Status.IN_TRANSIT,
        )
        staff = User.objects.create_superuser(
            username="shipment-status-admin",
            email="shipment-status-admin@example.com",
            password="Safe-pass-123",
        )
        self.client.force_login(staff)

        response = self.client.post(reverse("admin:store_shipment_change", args=[shipment.pk]), {
            "order": order.pk,
            "carrier": "Example Courier",
            "tracking_number": "TRACK-123",
            "tracking_url": "",
            "status": Shipment.Status.LABEL_CREATED,
            "estimated_delivery": "",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shipment status cannot move backwards.")
        shipment.refresh_from_db()
        self.assertEqual(shipment.status, Shipment.Status.IN_TRANSIT)

    def test_admin_cannot_add_shipment_to_cancelled_order(self):
        order = self.make_order(status=Order.Status.CANCELLED)
        staff = User.objects.create_superuser(
            username="cancelled-shipment-admin",
            email="cancelled-shipment-admin@example.com",
            password="Safe-pass-123",
        )
        self.client.force_login(staff)

        response = self.client.post(reverse("admin:store_shipment_add"), {
            "order": order.pk,
            "carrier": "Example Courier",
            "tracking_number": "TRACK-CANCELLED",
            "tracking_url": "",
            "status": Shipment.Status.IN_TRANSIT,
            "estimated_delivery": "",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A shipment cannot be created or updated for a cancelled order.")
        self.assertFalse(Shipment.objects.filter(order=order).exists())

    def test_admin_can_update_tracking_details_and_customer_sees_them(self):
        owner = User.objects.create_user(
            username="shipment-update-owner",
            email="shipment-update-owner@example.com",
            password="Safe-pass-123",
        )
        order = self.make_order(user=owner, email=owner.email)
        shipment = Shipment.objects.create(order=order)
        staff = User.objects.create_superuser(
            username="shipment-update-admin",
            email="shipment-update-admin@example.com",
            password="Safe-pass-123",
        )
        self.client.force_login(staff)

        response = self.client.post(reverse("admin:store_shipment_change", args=[shipment.pk]), {
            "order": order.pk,
            "carrier": "Updated Courier",
            "tracking_number": "UPDATED-123",
            "tracking_url": "https://courier.example/track/UPDATED-123",
            "status": Shipment.Status.LABEL_CREATED,
            "estimated_delivery": "2026-11-27",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 302)
        self.client.force_login(owner)
        detail = self.client.get(reverse("accounts:order_detail", args=[order.number]))
        self.assertContains(detail, "Updated Courier")
        self.assertContains(detail, "UPDATED-123")
        self.assertContains(detail, "27 Nov 2026")
        self.assertContains(detail, "https://courier.example/track/UPDATED-123")
        self.assertTrue(any("UPDATED-123" in email.body for email in mail.outbox))

    def test_admin_shipment_creation_updates_order_and_notifies_customer(self):
        owner = User.objects.create_user(
            username="shipment-owner",
            email="shipment-owner@example.com",
            password="Safe-pass-123",
        )
        order = self.make_order(user=owner, email=owner.email)
        staff = User.objects.create_superuser(
            username="shipment-create-admin",
            email="shipment-create-admin@example.com",
            password="Safe-pass-123",
        )
        self.client.force_login(staff)

        response = self.client.post(reverse("admin:store_shipment_add"), {
            "order": order.pk,
            "carrier": "Example Courier",
            "tracking_number": "TRACK-456",
            "tracking_url": "https://courier.example/track/TRACK-456",
            "status": Shipment.Status.IN_TRANSIT,
            "estimated_delivery": "2026-11-25",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 302)
        shipment = Shipment.objects.get(order=order)
        self.assertEqual(shipment.tracking_number, "TRACK-456")
        self.assertEqual(shipment.estimated_delivery.isoformat(), "2026-11-25")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertTrue(any("TRACK-456" in email.body for email in mail.outbox))

        self.client.force_login(owner)
        detail = self.client.get(reverse("accounts:order_detail", args=[order.number]))
        self.assertContains(detail, "TRACK-456")
        self.assertContains(detail, "25 Nov 2026")
        self.assertContains(detail, "https://courier.example/track/TRACK-456")

    def test_delivered_shipment_marks_order_delivered(self):
        order = self.make_order(status=Order.Status.SHIPPED)
        shipment = Shipment.objects.create(order=order, status=Shipment.Status.DELIVERED)
        record_shipment_update(shipment)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertIsNotNone(shipment.delivered_at)

    def test_customer_can_view_own_tracking_but_not_another_order(self):
        owner = User.objects.create_user(username="track-owner", email="owner@example.com", password="Safe-pass-123")
        other = User.objects.create_user(username="track-other", email="other@example.com", password="Safe-pass-123")
        order = self.make_order(user=owner, email=owner.email)
        Shipment.objects.create(order=order, carrier="Example Courier", tracking_number="OWN123")
        self.client.force_login(owner)
        response = self.client.get(reverse("accounts:order_detail", args=[order.number]))
        self.assertContains(response, "OWN123")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("accounts:order_detail", args=[order.number])).status_code, 404)

    def test_guest_order_owner_can_view_tracking_from_the_same_session(self):
        order = self.make_order()
        Shipment.objects.create(
            order=order,
            carrier="Example Courier",
            tracking_number="GUEST123",
            tracking_url="https://courier.example/track/GUEST123",
            estimated_delivery=date(2026, 11, 28),
        )
        session = self.client.session
        session["recent_orders"] = [order.number]
        session.save()

        response = self.client.get(reverse("store:order_success", args=[order.number]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GUEST123")
        self.assertContains(response, "28 Nov 2026")
        self.assertContains(response, "https://courier.example/track/GUEST123")

    def test_payment_success_sends_email(self):
        order = self.make_order()
        record_payment(order, Order.PaymentStatus.PAID)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("payment received", mail.outbox[0].subject.lower())
        self.assertIn(order.number, mail.outbox[0].body)

    def test_refund_status_sends_email(self):
        order = self.make_order(payment_status=Order.PaymentStatus.PAID, payment_method="razorpay")
        record_payment(order, Order.PaymentStatus.REFUNDED, provider_confirmed=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("refund", mail.outbox[0].subject.lower())
        self.assertIn(order.number, mail.outbox[0].body)

    def test_pending_payment_cannot_be_marked_refunded(self):
        order = self.make_order(payment_method="razorpay")

        with self.assertRaises(ValidationError):
            record_payment(order, Order.PaymentStatus.REFUNDED, provider_confirmed=True)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    def test_paid_payment_cannot_be_marked_refunded_without_provider_confirmation(self):
        order = self.make_order(payment_status=Order.PaymentStatus.PAID, payment_method="razorpay")

        with self.assertRaises(ValidationError):
            record_payment(order, Order.PaymentStatus.REFUNDED)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_online_payment_cannot_be_marked_paid_without_provider_confirmation(self):
        order = self.make_order(payment_method="razorpay")

        with self.assertRaises(ValidationError):
            record_payment(order, Order.PaymentStatus.PAID)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    def test_cancelled_order_cannot_be_marked_paid(self):
        order = self.make_order(status=Order.Status.CANCELLED)

        with self.assertRaises(ValidationError):
            record_payment(order, Order.PaymentStatus.PAID)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    def test_repeated_payment_status_does_not_duplicate_history_or_email(self):
        order = self.make_order()
        record_payment(order, Order.PaymentStatus.PAID)
        event_count = order.events.count()

        record_payment(order, Order.PaymentStatus.PAID)

        self.assertEqual(order.events.count(), event_count)
        self.assertEqual(len(mail.outbox), 1)

    def test_notification_delivery_failure_is_logged_without_blocking_order(self):
        order = self.make_order()
        with mock.patch("store.services.send_mail", side_effect=SMTPException("SMTP unavailable")) as send_mail:
            with self.assertLogs("store.services", level="ERROR") as log:
                self.assertEqual(send_order_notification(order, "placed"), 0)
        self.assertFalse(send_mail.call_args.kwargs["fail_silently"])
        self.assertIn(order.number, log.output[0])

    def test_paid_order_does_not_offer_customer_cancellation(self):
        owner = User.objects.create_user(
            username="paid-order-owner",
            email="paid-owner@example.com",
            password="Safe-pass-123",
        )
        order = self.make_order(user=owner, payment_status=Order.PaymentStatus.PAID)
        self.client.force_login(owner)
        response = self.client.get(reverse("accounts:order_detail", args=[order.number]))
        self.assertNotContains(response, "Cancel order")

    def test_paid_order_cancellation_is_rejected_by_order_service(self):
        order = self.make_order(payment_status=Order.PaymentStatus.PAID)
        with self.assertRaises(ValidationError):
            transition_order(order, Order.Status.CANCELLED)


class OrderAdminActionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="orders-admin",
            email="admin@example.com",
            password="Safe-admin-pass-123",
        )
        self.order = Order.objects.create(
            email="customer@example.com",
            phone="9876543210",
            subtotal=Decimal("500.00"),
            shipping_fee=Decimal("50.00"),
            total=Decimal("550.00"),
            shipping_address={"full_name": "Test Customer"},
        )
        self.client.force_login(self.admin)
        self.url = reverse("admin:store_order_changelist")

    def test_admin_can_confirm_order_through_validated_action(self):
        response = self.client.post(self.url, {
            "action": "mark_confirmed",
            "_selected_action": [self.order.pk],
            "index": "0",
        })
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        self.assertTrue(self.order.events.filter(status=Order.Status.CONFIRMED).exists())

    def test_admin_search_and_status_filter_find_orders(self):
        response = self.client.get(self.url, {
            "q": "customer@example.com",
            "status__exact": Order.Status.PLACED,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cl"].queryset), [self.order])

    def test_admin_cannot_ship_unpaid_razorpay_order(self):
        self.order.payment_method = "razorpay"
        self.order.save(update_fields=["payment_method", "updated_at"])

        self.client.post(self.url, {
            "action": "mark_shipped",
            "_selected_action": [self.order.pk],
            "index": "0",
        })

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PLACED)

    def test_admin_cancellation_returns_stock_and_records_audit_event(self):
        category = Category.objects.create(name="Admin Action Plants")
        product = Product.objects.create(name="Admin Action Plant", category=category)
        variant = ProductVariant.objects.create(
            product=product,
            sku="ADMIN-ACTION-1",
            price=Decimal("100.00"),
            stock=5,
        )
        OrderItem.objects.create(
            order=self.order,
            variant=variant,
            product_name=product.name,
            variant_name=variant.name,
            sku=variant.sku,
            unit_price=Decimal("100.00"),
            quantity=2,
            line_total=Decimal("200.00"),
        )
        StockMovement.objects.create(
            variant=variant,
            change=-2,
            reason=StockMovement.Reason.SALE,
            order=self.order,
        )

        response = self.client.post(self.url, {
            "action": "mark_cancelled",
            "_selected_action": [self.order.pk],
            "index": "0",
        })

        self.assertEqual(response.status_code, 302)
        variant.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(variant.stock, 5)
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertTrue(self.order.events.filter(status=Order.Status.CANCELLED).exists())
        self.assertTrue(self.order.stock_movements.filter(reason=StockMovement.Reason.CANCELLATION).exists())

    def test_admin_cannot_refund_an_unpaid_order(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'value="mark_payment_refunded"')

    def test_admin_cannot_mark_paid_order_refunded_without_provider_confirmation(self):
        self.order.payment_status = Order.PaymentStatus.PAID
        self.order.save(update_fields=["payment_status", "updated_at"])

        self.client.get(self.url)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_admin_cannot_manually_mark_razorpay_order_paid(self):
        self.order.payment_method = "razorpay"
        self.order.save(update_fields=["payment_method", "updated_at"])

        self.client.post(self.url, {
            "action": "mark_payment_paid",
            "_selected_action": [self.order.pk],
            "index": "0",
        })

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
