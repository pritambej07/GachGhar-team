import hashlib
import hmac
import json
import logging
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Cart, Order, OrderEvent, RazorpayWebhookEvent
from .payments import get_client, verify_checkout_signature, amount_in_paise
from .services import record_payment, send_order_notification

logger = logging.getLogger(__name__)
MAX_WEBHOOK_AMOUNT_PAISE = 9_999_999_999
WEBHOOK_RATE_LIMIT_KEY = "razorpay_webhook_rate_limit"
WEBHOOK_RATE_LIMIT_WINDOW = 60  # seconds
WEBHOOK_RATE_LIMIT_MAX = 30  # requests per window


def _notify_paid_order(order):
    try:
        send_order_notification(order, "payment_paid")
    except Exception:
        logger.exception("Could not send verified-payment notification for %s", order.number)


def _empty_paid_order_cart(order, request=None):
    """Remove purchased lines only after provider-confirmed payment."""
    if request is not None:
        from .services import get_cart
        cart = get_cart(request, create=False)
    elif order.user_id:
        cart = Cart.objects.filter(user_id=order.user_id).first()
    else:
        # Guest orders have no durable cart association on Order. The checkout
        # callback can clear it from the session; webhooks cannot identify it.
        cart = None
    if cart is not None:
        variant_ids = order.items.values_list("variant_id", flat=True)
        cart.items.filter(variant_id__in=variant_ids).delete()


def _verify_razorpay_webhook_signature(payload_bytes, signature):
    """Verify Razorpay webhook signature using the webhook secret.

    Razorpay sends an X-Razorpay-Signature header that is an HMAC-SHA256
    of the raw body using RAZORPAY_WEBHOOK_SECRET as the key.
    Returns True if valid, False otherwise.
    """
    webhook_secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "") or ""
    if not webhook_secret:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not configured; rejecting webhook.")
        return False
    if not signature:
        return False
    expected = hmac.new(
        webhook_secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _webhook_rate_limited(request):
    """Basic rate limiting for webhook endpoint to prevent abuse."""
    remote_addr = request.META.get("REMOTE_ADDR", "unknown")
    key = f"{WEBHOOK_RATE_LIMIT_KEY}:{remote_addr}"
    current = cache.get(key, 0)
    if current >= WEBHOOK_RATE_LIMIT_MAX:
        return True
    cache.add(key, 0, WEBHOOK_RATE_LIMIT_WINDOW)
    cache.incr(key)
    return False


def _webhook_amount(raw_amount):
    if isinstance(raw_amount, bool):
        return None
    if isinstance(raw_amount, int):
        amount = raw_amount
    elif isinstance(raw_amount, str) and raw_amount.isascii() and raw_amount.isdigit() and len(raw_amount) <= 10:
        amount = int(raw_amount)
    else:
        return None
    return amount if 0 < amount <= MAX_WEBHOOK_AMOUNT_PAISE else None


@require_POST
def verify_payment(request):
    oid = request.POST.get("razorpay_order_id", "")
    pid = request.POST.get("razorpay_payment_id", "")
    sig = request.POST.get("razorpay_signature", "")
    order = get_object_or_404(Order, razorpay_order_id=oid)
    is_owner = request.user.is_authenticated and order.user_id == request.user.pk
    is_guest_owner = order.number in request.session.get("recent_orders", [])
    if not (is_owner or is_guest_owner):
        return HttpResponse("Unauthorized", status=403)
    if order.payment_status == Order.PaymentStatus.REFUNDED:
        return HttpResponse("This payment has already been refunded.", status=400)
    try:
        verify_checkout_signature(oid, pid, sig)
        payment = get_client().payment.fetch(pid)
        if (
            payment.get("status") != "captured"
            or int(payment.get("amount", 0)) != amount_in_paise(order.total)
            or payment.get("currency") != "INR"
            or payment.get("order_id") != oid
        ):
            return HttpResponse("Payment not verified/captured", status=400)
        payment_changed = False
        already_processed = False
        conflicting_payment = False
        was_refunded = False
        was_cancelled = False
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
            if locked.status == Order.Status.CANCELLED:
                was_cancelled = True
            elif locked.payment_status == Order.PaymentStatus.REFUNDED:
                was_refunded = True
            elif locked.payment_status == Order.PaymentStatus.PAID:
                already_processed = locked.razorpay_payment_id == pid
                conflicting_payment = not already_processed
            elif locked.payment_status != Order.PaymentStatus.PAID:
                locked.payment_status = Order.PaymentStatus.PAID
                locked.razorpay_payment_id = pid
                locked.payment_verified_at = timezone.now()
                locked.save(update_fields=[
                    "payment_status", "razorpay_payment_id",
                    "payment_verified_at", "updated_at"
                ])
                payment_changed = True
        if was_cancelled:
            logger.error(
                "Captured payment %s received for cancelled order %s; manual reconciliation is required",
                pid, order.number,
            )
            return HttpResponse(
                "This order was cancelled. Contact support regarding the captured payment.",
                status=400,
            )
        if was_refunded:
            return HttpResponse("This payment has already been refunded.", status=400)
        if conflicting_payment:
            return HttpResponse("A different payment has already been recorded for this order.", status=400)
        if payment_changed:
            _empty_paid_order_cart(locked, request=request)
            _notify_paid_order(locked)
        elif already_processed:
            _empty_paid_order_cart(locked, request=request)
        return redirect("store:order_success", number=order.number)
    except Exception:
        logger.exception("Razorpay checkout verification failed for %s", order.number)
        return HttpResponse("Payment verification failed. Please retry or contact support.", status=400)


def _processed_refund_total(payment_id, current_event, current_amount):
    total = current_amount
    processed_events = RazorpayWebhookEvent.objects.filter(
        event_type="refund.processed",
        processed=True,
    ).exclude(pk=current_event.pk).only("payload")
    for event in processed_events:
        payload = event.payload
        payload_data = payload.get("payload") if isinstance(payload, dict) else None
        refund = payload_data.get("refund") if isinstance(payload_data, dict) else None
        entity = refund.get("entity", {}) if isinstance(refund, dict) else {}
        if (
            isinstance(entity, dict)
            and entity.get("payment_id") == payment_id
            and entity.get("currency") == "INR"
            and entity.get("status") == "processed"
        ):
            amount = _webhook_amount(entity.get("amount"))
            if amount is not None:
                total += amount
    return total


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    if _webhook_rate_limited(request):
        return HttpResponse("Rate limited", status=429)
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not secret or not signature:
        return HttpResponse("Webhook not configured", status=400)
    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return HttpResponse("Invalid signature", status=400)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse("Invalid webhook payload", status=400)
    if not isinstance(data, dict) or not isinstance(data.get("event"), str) or not data["event"]:
        return HttpResponse("Invalid webhook payload", status=400)

    event_type = data["event"]
    entity = None
    amount = None
    refund_entity = None
    if event_type == "payment.captured":
        payload = data.get("payload")
        payment = payload.get("payment") if isinstance(payload, dict) else None
        entity = payment.get("entity") if isinstance(payment, dict) else None
        raw_amount = entity.get("amount") if isinstance(entity, dict) else None
        amount = _webhook_amount(raw_amount)
        if (
            not isinstance(entity, dict)
            or not isinstance(entity.get("order_id"), str)
            or not entity["order_id"]
            or not isinstance(entity.get("id"), str)
            or not entity["id"]
            or not isinstance(entity.get("currency"), str)
            or amount is None
        ):
            return HttpResponse("Invalid payment webhook payload", status=400)
    elif event_type == "refund.processed":
        payload = data.get("payload")
        refund = payload.get("refund") if isinstance(payload, dict) else None
        refund_entity = refund.get("entity") if isinstance(refund, dict) else None
        raw_amount = refund_entity.get("amount") if isinstance(refund_entity, dict) else None
        amount = _webhook_amount(raw_amount)
        if (
            not isinstance(refund_entity, dict)
            or refund_entity.get("status") != "processed"
            or not isinstance(refund_entity.get("id"), str)
            or not refund_entity["id"]
            or not isinstance(refund_entity.get("payment_id"), str)
            or not refund_entity["payment_id"]
            or refund_entity.get("currency") != "INR"
            or amount is None
        ):
            return HttpResponse("Invalid refund webhook payload", status=400)

    try:
        event_id = request.headers.get("X-Razorpay-Event-Id") or hashlib.sha256(request.body).hexdigest()
        if len(event_id) > 100:
            return HttpResponse("Invalid webhook event ID", status=400)
        event, _ = RazorpayWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={"event_type": event_type, "payload": data}
        )
        if event.processed:
            return HttpResponse("Duplicate OK")
        if entity is not None:
            order = Order.objects.filter(razorpay_order_id=entity["order_id"]).first()
            if order and amount == amount_in_paise(order.total) and entity["currency"] == "INR":
                payment_changed = False
                with transaction.atomic():
                    locked = Order.objects.select_for_update().get(pk=order.pk)
                    if locked.status == Order.Status.CANCELLED:
                        logger.error(
                            "Captured payment %s received for cancelled order %s; manual reconciliation is required",
                            entity["id"], order.number,
                        )
                    elif locked.payment_status == Order.PaymentStatus.REFUNDED:
                        logger.warning("Captured payment event received for refunded order %s", locked.number)
                    elif locked.payment_status != Order.PaymentStatus.PAID:
                        locked.payment_status = Order.PaymentStatus.PAID
                        locked.razorpay_payment_id = entity["id"]
                        locked.payment_verified_at = timezone.now()
                        locked.save(update_fields=[
                            "payment_status", "razorpay_payment_id",
                            "payment_verified_at", "updated_at"
                        ])
                        payment_changed = True
                if payment_changed:
                    _empty_paid_order_cart(locked)
                    _notify_paid_order(locked)
        elif refund_entity is not None:
            order = Order.objects.filter(
                payment_method="razorpay",
                razorpay_payment_id=refund_entity["payment_id"],
            ).first()
            if order and refund_entity["currency"] == "INR":
                if order.payment_status == Order.PaymentStatus.PENDING:
                    logger.error(
                        "Processed refund %s received before payment was verified for order %s",
                        refund_entity["id"],
                        order.number,
                    )
                    return HttpResponse("Payment must be verified before processing its refund.", status=500)
                refunded_total = _processed_refund_total(
                    refund_entity["payment_id"],
                    event,
                    amount,
                )
                if refunded_total >= amount_in_paise(order.total):
                    record_payment(
                        order,
                        Order.PaymentStatus.REFUNDED,
                        note=f"Razorpay refund {refund_entity['id']} was confirmed as processed "
                             f"(cumulative INR {refunded_total / 100:.2f}).",
                        provider_confirmed=True,
                    )
                elif order.payment_status == Order.PaymentStatus.PAID:
                    OrderEvent.objects.create(
                        order=order,
                        status=order.status,
                        note=f"Razorpay partial refund {refund_entity['id']} processed "
                             f"(INR {amount / 100:.2f}); payment remains partially refunded.",
                    )
                else:
                    logger.warning(
                        "Refund %s confirmed for already-refunded order %s",
                        refund_entity["id"],
                        order.number,
                    )
        event.processed = True
        event.save(update_fields=["processed"])
        return HttpResponse("OK")
    except Exception:
        logger.exception("Razorpay webhook processing failed")
        return HttpResponse("Webhook processing error", status=500)
