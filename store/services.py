"""Business logic for catalogue queries, carts, checkout, and order state changes.

Views stay thin: all prices, stock checks, and totals are calculated here on the server.
"""
import secrets
import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Min, Sum
from django.utils import timezone

from .models import (Cart, CartItem, Coupon, CouponRedemption, Order, OrderEvent, OrderItem, Product, ProductVariant, SiteSettings,
                     StockMovement, Shipment)

GUEST_CART_KEY = "guest_cart_token"
ZERO = Decimal("0.00")
logger = logging.getLogger(__name__)


def max_quantity():
    return settings.CART_MAX_QUANTITY




# ---------- customer email notifications ----------

ORDER_EMAILS = {
    "placed": ("We received your GachGhar order", "Your order has been placed and is being processed."),
    "confirmed": ("Your GachGhar order is confirmed", "Your order has been confirmed by our team."),
    "shipped": ("Your GachGhar order has been shipped", "Your order is on its way."),
    "delivered": ("Your GachGhar order was delivered", "Your order has been marked as delivered."),
    "cancelled": ("Your GachGhar order was cancelled", "Your order has been cancelled."),
    "payment_paid": ("Payment received for your GachGhar order", "We have verified your payment."),
    "payment_refunded": ("Refund updated for your GachGhar order", "Your order payment has been marked as refunded."),
    "shipment_update": ("Your GachGhar shipment was updated", "There is a new update for your shipment."),
}


def send_order_notification(order, event, shipment=None):
    """Send a best-effort customer email. A mail server failure never blocks an order update."""
    email = order.email or (order.user.email if order.user_id and order.user else "")
    template = ORDER_EMAILS.get(event)
    if not email or not template:
        return 0

    subject, intro = template
    lines = [
        f"Hello {order.shipping_address.get('full_name', 'Customer')},",
        "",
        intro,
        f"Order: {order.number}",
        f"Order status: {order.get_status_display()}",
        f"Payment status: {order.get_payment_status_display()}",
        f"Order total: Rs. {order.total}",
    ]
    if shipment is None:
        try:
            shipment = order.shipment
        except Shipment.DoesNotExist:
            shipment = None
    if shipment:
        lines.extend([
            "",
            f"Carrier: {shipment.carrier or 'Not specified'}",
            f"Tracking number: {shipment.tracking_number or 'Not available'}",
            f"Shipment status: {shipment.get_status_display()}",
        ])
        if shipment.estimated_delivery:
            lines.append(f"Estimated delivery: {shipment.estimated_delivery:%d %b %Y}")
        if shipment.tracking_url:
            lines.append(f"Track shipment: {shipment.tracking_url}")
    lines.extend(["", "Thank you for choosing GachGhar.", "GachGhar Team"])
    try:
        return send_mail(
            subject,
            "\n".join(lines),
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Could not send order notification for %s", order.number)
        return 0


def record_shipment_update(shipment, actor=None, created=False):
    """Append a shipment event and keep the order lifecycle in sync with carrier milestones."""
    order = shipment.order
    note = (
        "Shipment tracking information added."
        if created else f"Shipment status updated: {shipment.get_status_display()}."
    )
    if shipment.tracking_number:
        note += f" Tracking number: {shipment.tracking_number}."
    transitioned = False

    moving_statuses = {
        Shipment.Status.PICKED_UP,
        Shipment.Status.IN_TRANSIT,
        Shipment.Status.OUT_FOR_DELIVERY,
        Shipment.Status.DELIVERED,
    }
    if shipment.status in moving_statuses and order.status == Order.Status.PLACED:
        order = transition_order(order, Order.Status.CONFIRMED, actor=actor,
                                 note="Order confirmed from carrier update.")
        transitioned = True

    if shipment.status in moving_statuses and order.status == Order.Status.CONFIRMED:
        order = transition_order(order, Order.Status.SHIPPED, actor=actor,
                                 note="Shipment handed to carrier.")
        transitioned = True

    if shipment.status == Shipment.Status.DELIVERED and order.status == Order.Status.SHIPPED:
        order = transition_order(order, Order.Status.DELIVERED, actor=actor,
                                 note="Carrier marked shipment as delivered.")
        transitioned = True

    if not transitioned:
        OrderEvent.objects.create(order=order, status=order.status, note=note, actor=actor)
        send_order_notification(order, "shipment_update", shipment=shipment)

# ---------- catalogue ----------

def visible_products():
    """Active products that have at least one active variant, annotated with price and stock."""
    return (Product.objects.filter(is_active=True, variants__is_active=True)
            .annotate(min_price=Min("variants__price"), total_stock=Sum("variants__stock"),
                      variant_count=Count("variants"))
            .select_related("category").prefetch_related("images"))


# ---------- carts ----------

def get_cart(request, create=True):
    if request.user.is_authenticated:
        if create:
            cart, _ = Cart.objects.get_or_create(user=request.user)
            return cart
        return Cart.objects.filter(user=request.user).first()
    token = request.session.get(GUEST_CART_KEY)
    if not token:
        if not create:
            return None
        token = secrets.token_urlsafe(32)
        request.session[GUEST_CART_KEY] = token
    if create:
        cart, _ = Cart.objects.get_or_create(guest_token=token)
        return cart
    return Cart.objects.filter(guest_token=token).first()


def cart_item_count(request):
    cart = get_cart(request, create=False)
    if cart is None:
        return 0
    return cart.items.aggregate(total=Sum("quantity"))["total"] or 0


def merge_guest_cart(request, user):
    """Move the guest cart into the user's cart on login, combining quantities safely."""
    token = request.session.pop(GUEST_CART_KEY, None)
    if not token:
        return
    guest = Cart.objects.filter(guest_token=token).first()
    if guest is None:
        return
    with transaction.atomic():
        user_cart, _ = Cart.objects.get_or_create(user=user)
        for item in guest.items.all():
            existing = user_cart.items.filter(variant_id=item.variant_id).first()
            if existing:
                existing.quantity = min(existing.quantity + item.quantity, max_quantity())
                existing.save(update_fields=["quantity"])
            else:
                user_cart.items.create(variant_id=item.variant_id, quantity=min(item.quantity, max_quantity()))
        guest.delete()


def add_to_cart(cart, variant_id, quantity):
    if not 1 <= quantity <= max_quantity():
        raise ValidationError(f"Quantity must be between 1 and {max_quantity()}.")
    with transaction.atomic():
        variant = ProductVariant.objects.select_for_update().select_related("product").get(pk=variant_id)
        if not (variant.is_active and variant.product.is_active):
            raise ValidationError("This product is not available right now.")
        item = CartItem.objects.select_for_update().filter(cart=cart, variant=variant).first()
        new_qty = (item.quantity if item else 0) + quantity
        if new_qty > max_quantity():
            raise ValidationError(f"You can add up to {max_quantity()} of one item.")
        if new_qty > variant.stock:
            raise ValidationError(f"Only {variant.stock} left in stock.")
        if item:
            item.quantity = new_qty
            item.save(update_fields=["quantity"])
        else:
            item = CartItem.objects.create(cart=cart, variant=variant, quantity=new_qty)
    return item


def set_cart_quantity(item, quantity):
    """Set a line's quantity. Zero or less removes the line."""
    if quantity <= 0:
        item.delete()
        return None
    if quantity > max_quantity():
        raise ValidationError(f"You can add up to {max_quantity()} of one item.")
    with transaction.atomic():
        variant = ProductVariant.objects.select_for_update().get(pk=item.variant_id)
        if quantity > variant.stock:
            raise ValidationError(f"Only {variant.stock} left in stock.")
        item.quantity = quantity
        item.save(update_fields=["quantity"])
    return item


def shipping_fee_for(subtotal):
    site = SiteSettings.load()
    if subtotal <= 0:
        return ZERO
    if site.free_shipping_threshold is not None and subtotal >= site.free_shipping_threshold:
        return ZERO
    return site.shipping_fee


def cart_summary(cart):
    lines, subtotal, count, has_issues = [], ZERO, 0, False
    items = cart.items.select_related("variant__product").prefetch_related("variant__product__images") if cart else []
    for item in items:
        variant = item.variant
        available = variant.is_active and variant.product.is_active
        in_stock = available and variant.stock >= item.quantity
        has_issues = has_issues or not in_stock
        line_total = variant.price * item.quantity if available else ZERO
        subtotal += line_total
        count += item.quantity
        image = variant.product.images.all()
        lines.append({
            "id": item.pk, "variant_id": variant.pk, "product_name": variant.product.name,
            "variant_name": variant.name, "url": variant.product.get_absolute_url(),
            "image_url": image[0].image.url if image else "", "unit_price": variant.price,
            "quantity": item.quantity, "line_total": line_total, "available": available,
            "in_stock": in_stock, "stock": variant.stock,
        })
    shipping = shipping_fee_for(subtotal)
    return {"lines": lines, "count": count, "subtotal": subtotal, "shipping": shipping,
            "total": subtotal + shipping, "has_issues": has_issues}


# ---------- coupons ----------

CENT = Decimal("0.01")


def compute_coupon_discount(coupon, lines, subtotal):
    """Validate a coupon against (variant, quantity) lines and return the discount. Raises ValidationError.

    Everything is calculated from database prices. The discount can never exceed the eligible subtotal.
    """
    now = timezone.now()
    if coupon is None or not coupon.is_active:
        raise ValidationError("This coupon code is not valid.")
    if coupon.starts_at and now < coupon.starts_at:
        raise ValidationError("This coupon is not active yet.")
    if coupon.ends_at and now > coupon.ends_at:
        raise ValidationError("This coupon has expired.")
    if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
        raise ValidationError("This coupon has reached its usage limit.")
    if subtotal < coupon.min_order_value:
        raise ValidationError(f"This coupon needs a minimum order of \u20b9{coupon.min_order_value:.2f}.")
    product_ids = set(coupon.products.values_list("pk", flat=True))
    category_ids = set()
    for category in coupon.categories.all():
        category_ids.update(category.descendant_ids())
    restricted = bool(product_ids or category_ids)
    eligible = ZERO
    for variant, quantity in lines:
        if not restricted or variant.product_id in product_ids or variant.product.category_id in category_ids:
            eligible += variant.price * quantity
    if eligible <= 0:
        raise ValidationError("This coupon does not apply to the items in your cart.")
    if coupon.discount_type == Coupon.DiscountType.PERCENT:
        discount = (eligible * coupon.value / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        discount = coupon.value
    return min(discount, eligible).quantize(CENT)


def quote_coupon(cart, code):
    """Preview a coupon for the checkout page. Returns (coupon, discount). Raises ValidationError."""
    coupon = Coupon.objects.filter(code=(code or "").strip().upper()).first()
    items = list(cart.items.select_related("variant__product")) if cart else []
    lines = [(i.variant, i.quantity) for i in items]
    subtotal = sum((v.price * q for v, q in lines), ZERO)
    return coupon, compute_coupon_discount(coupon, lines, subtotal)


# ---------- checkout ----------

def create_order(*, cart, user, data, idempotency_key, payment_method, coupon_code=""):
    """Validate the cart under row locks, then create the order, stock movements and snapshots atomically."""
    if not cart or not cart.items.exists():
        raise ValidationError("Your cart is empty.")
    with transaction.atomic():
        items = list(cart.items.all())
        variants = {v.pk: v for v in ProductVariant.objects.select_for_update()
                    .select_related("product").filter(pk__in=[i.variant_id for i in items])}
        plan, subtotal = [], ZERO
        for item in items:
            variant = variants[item.variant_id]
            if not (variant.is_active and variant.product.is_active):
                raise ValidationError(f"{variant.product.name} is no longer available. Please update your cart.")
            if variant.stock < item.quantity:
                raise ValidationError(f"Only {variant.stock} of {variant.product.name} ({variant.name}) left. "
                                      "Please update your cart.")
            plan.append((item, variant))
            subtotal += variant.price * item.quantity
        coupon, discount = None, ZERO
        if coupon_code:
            coupon = Coupon.objects.select_for_update().filter(code=coupon_code.strip().upper()).first()
            discount = compute_coupon_discount(coupon, [(v, i.quantity) for i, v in plan], subtotal)
        shipping = shipping_fee_for(subtotal)
        order = Order.objects.create(
            user=user if user.is_authenticated else None,
            idempotency_key=idempotency_key,
            email=data.get("email") or (user.email if user.is_authenticated else ""),
            phone=data["phone"],
            payment_method=payment_method,
            subtotal=subtotal,
            discount_total=discount,
            coupon_code=coupon.code if coupon else "",
            shipping_fee=shipping,
            total=subtotal - discount + shipping,
            shipping_address={
                "full_name": data["full_name"], "phone": data["phone"], "line1": data["line1"],
                "line2": data.get("line2", ""), "city": data["city"], "state": data["state"],
                "pincode": data["pincode"], "country": "India",
            },
        )
        for item, variant in plan:
            line_total = variant.price * item.quantity
            OrderItem.objects.create(order=order, variant=variant, product_name=variant.product.name,
                                     variant_name=variant.name, sku=variant.sku, unit_price=variant.price,
                                     quantity=item.quantity, line_total=line_total)
            StockMovement.objects.create(variant=variant, change=-item.quantity, reason=StockMovement.Reason.SALE,
                                         order=order, note=f"Order {order.number}")
        if coupon:
            CouponRedemption.objects.create(coupon=coupon, order=order, discount_amount=discount,
                                            user=user if user.is_authenticated else None)
        OrderEvent.objects.create(order=order, status=order.status, note="Order placed.",
                                  actor=user if user.is_authenticated else None)
        # Online orders retain their cart until Razorpay confirms payment.
        # COD orders have no asynchronous payment step, so preserve existing
        # checkout behavior for those orders.
        if payment_method != "razorpay":
            cart.items.all().delete()
    send_order_notification(order, "placed")
    return order


# ---------- order state ----------

ALLOWED_TRANSITIONS = {
    Order.Status.PLACED: {Order.Status.CONFIRMED, Order.Status.CANCELLED},
    Order.Status.CONFIRMED: {Order.Status.SHIPPED, Order.Status.CANCELLED},
    Order.Status.SHIPPED: {Order.Status.DELIVERED},
    Order.Status.DELIVERED: set(),
    Order.Status.CANCELLED: set(),
}

ALLOWED_PAYMENT_TRANSITIONS = {
    Order.PaymentStatus.PENDING: {Order.PaymentStatus.PAID},
    Order.PaymentStatus.PAID: {Order.PaymentStatus.REFUNDED},
    Order.PaymentStatus.REFUNDED: set(),
}


def transition_order(order, new_status, actor=None, note=""):
    """Move an order to a permitted next state, recording an event. Cancelling returns stock."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if new_status == Order.Status.CANCELLED and order.payment_status == Order.PaymentStatus.PAID:
            raise ValidationError("A paid order must be refunded before it can be cancelled.")
        if (
            new_status == Order.Status.SHIPPED
            and order.payment_method == "razorpay"
            and order.payment_status != Order.PaymentStatus.PAID
        ):
            raise ValidationError("Verify the online payment before shipping this order.")
        if new_status not in ALLOWED_TRANSITIONS[order.status]:
            raise ValidationError(f"An order cannot move from {order.get_status_display()} to "
                                  f"{Order.Status(new_status).label}.")
        if new_status == Order.Status.CANCELLED:
            for item in order.items.select_related("variant"):
                StockMovement.objects.create(variant=item.variant, change=item.quantity,
                                             reason=StockMovement.Reason.CANCELLATION, order=order,
                                             created_by=actor, note=f"Order {order.number} cancelled")
        order.status = new_status
        order.save(update_fields=["status", "updated_at"])
        OrderEvent.objects.create(order=order, status=new_status, note=note, actor=actor)
    send_order_notification(order, new_status)
    return order


def record_payment(order, payment_status, actor=None, note="", provider_confirmed=False):
    if payment_status not in Order.PaymentStatus.values:
        raise ValidationError("Invalid payment status.")
    changed = False
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        changed = order.payment_status != payment_status
        if changed:
            if payment_status == Order.PaymentStatus.PAID and order.status == Order.Status.CANCELLED:
                raise ValidationError("A cancelled order cannot be marked paid.")
            if (
                payment_status == Order.PaymentStatus.PAID
                and order.payment_method == "razorpay"
                and not provider_confirmed
            ):
                raise ValidationError("Verify the online payment with the provider before marking it paid.")
            if payment_status == Order.PaymentStatus.REFUNDED and (
                order.payment_method != "razorpay" or not provider_confirmed
            ):
                raise ValidationError("A refund can only be marked complete after provider confirmation.")
            if payment_status not in ALLOWED_PAYMENT_TRANSITIONS[order.payment_status]:
                raise ValidationError(
                    f"Payment cannot move from {order.get_payment_status_display()} to "
                    f"{Order.PaymentStatus(payment_status).label}."
                )
            order.payment_status = payment_status
            order.save(update_fields=["payment_status", "updated_at"])
            OrderEvent.objects.create(
                order=order,
                status=order.status,
                note=note or f"Payment status set to {order.get_payment_status_display()}.",
                actor=actor,
            )
    if changed and payment_status == Order.PaymentStatus.PAID:
        send_order_notification(order, "payment_paid")
    elif changed and payment_status == Order.PaymentStatus.REFUNDED:
        send_order_notification(order, "payment_refunded")
    return order
