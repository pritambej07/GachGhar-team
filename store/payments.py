"""Razorpay server-side helpers for GachGhar."""
from decimal import Decimal, ROUND_HALF_UP
import razorpay
from django.conf import settings
def is_configured():
    # Accept both test (rzp_test_) and live (rzp_live_) keys.
    # Test mode is recommended for development; live keys should only be used
    # when the production payment integration is fully verified.
    return bool(
        (settings.RAZORPAY_KEY_ID.startswith("rzp_test_")
         or settings.RAZORPAY_KEY_ID.startswith("rzp_live_"))
        and settings.RAZORPAY_KEY_SECRET
    )
def get_client():
    if not is_configured():
        raise RuntimeError("Razorpay keys are not configured.")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
def amount_in_paise(amount):
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
def create_gateway_order(order):
    client = get_client()
    return client.order.create(data={
        "amount": amount_in_paise(order.total),
        "currency": "INR",
        "receipt": order.number,
        "notes": {"gachghar_order_number": order.number},
    })
def verify_checkout_signature(order_id, payment_id, signature):
    client = get_client()
    client.utility.verify_payment_signature({
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature,
    })
    return True