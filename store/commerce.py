"""Cart, wishlist, checkout and order-confirmation views. All money and stock checks happen server-side."""
import logging
import secrets
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.models import Address
from .formatting import format_inr
from .forms import CheckoutForm
from .payments import amount_in_paise, is_configured, create_gateway_order
from .models import Order, Product, ProductVariant, CartItem, SiteSettings, WishlistItem
from .services import (add_to_cart, cart_summary, create_order, get_cart, quote_coupon, set_cart_quantity,
                       shipping_fee_for, visible_products)
from .views import _safe_next

CHECKOUT_TOKEN_KEY = "checkout_token"
RECENT_ORDERS_KEY = "recent_orders"
COUPON_KEY = "coupon_code"
logger = logging.getLogger(__name__)


def wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


def cart_payload(request, message="", ok=True):
    summary = cart_summary(get_cart(request, create=False))
    return {
        "ok": ok, "message": message, "count": summary["count"],
        "subtotal": format_inr(summary["subtotal"]), "shipping": format_inr(summary["shipping"]),
        "total": format_inr(summary["total"]), "has_issues": summary["has_issues"],
        "lines": [{
            "id": line["id"], "name": line["product_name"], "variant": line["variant_name"],
            "url": line["url"], "image_url": line["image_url"], "quantity": line["quantity"],
            "unit_price": format_inr(line["unit_price"]), "line_total": format_inr(line["line_total"]),
            "available": line["available"], "in_stock": line["in_stock"], "stock": line["stock"],
        } for line in summary["lines"]],
    }


def _respond(request, message, ok, default_url):
    if wants_json(request):
        return JsonResponse(cart_payload(request, message, ok), status=200 if ok else 400)
    (messages.success if ok else messages.error)(request, message)
    return redirect(_safe_next(request, default_url))


def cart_page(request):
    summary = cart_summary(get_cart(request, create=False))
    return render(request, "store/cart.html", {"summary": summary})


def cart_api(request):
    return JsonResponse(cart_payload(request))


@require_POST
def cart_add(request):
    try:
        variant_id = int(request.POST.get("variant_id", ""))
        quantity = int(request.POST.get("quantity", "1"))
    except ValueError:
        return _respond(request, "Please choose a valid product option.", False, "store:products")
    try:
        add_to_cart(get_cart(request), variant_id, quantity)
    except (ValidationError, ProductVariant.DoesNotExist) as error:
        message = " ".join(error.messages) if isinstance(error, ValidationError) else "This option is not available."
        return _respond(request, message, False, "store:products")
    if request.POST.get("buy_now"):
        if wants_json(request):
            return JsonResponse({"ok": True, "redirect": reverse("store:checkout")})
        return redirect("store:checkout")
    return _respond(request, "Added to your cart.", True, "store:cart")


@require_POST
def cart_update(request, item_id):
    cart = get_cart(request, create=False)
    if cart is None:
        raise Http404
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    try:
        quantity = int(request.POST.get("quantity", "0"))
        set_cart_quantity(item, quantity)
    except ValueError:
        return _respond(request, "Please enter a valid quantity.", False, "store:cart")
    except ValidationError as error:
        return _respond(request, " ".join(error.messages), False, "store:cart")
    return _respond(request, "Cart updated.", True, "store:cart")


@login_required
def wishlist_page(request):
    products = visible_products().filter(wishlisted_by__user=request.user)
    return render(request, "store/wishlist.html", {"products": products})


@login_required
@require_POST
def wishlist_toggle(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    entry, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
    if not created:
        entry.delete()
    message = "Saved to your wishlist." if created else "Removed from your wishlist."
    if wants_json(request):
        return JsonResponse({"ok": True, "in_wishlist": created, "message": message})
    messages.success(request, message)
    return redirect(_safe_next(request, "store:wishlist"))


@login_required
@require_POST
def wishlist_to_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    variant = product.variants.filter(is_active=True, stock__gt=0).order_by("sort_order", "price").first()
    if variant is None:
        messages.error(request, "This product is out of stock right now.")
        return redirect("store:wishlist")
    try:
        add_to_cart(get_cart(request), variant.pk, 1)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("store:wishlist")
    WishlistItem.objects.filter(user=request.user, product=product).delete()
    messages.success(request, "Moved to your cart.")
    return redirect("store:cart")


def _checkout_initial(request):
    if not request.user.is_authenticated:
        return {}
    initial = {"email": request.user.email}
    profile = getattr(request.user, "profile", None)
    if profile and profile.phone:
        initial["phone"] = profile.phone
    address = Address.objects.filter(user=request.user, is_default=True).first()
    if address:
        initial.update({"full_name": address.full_name, "phone": address.phone, "line1": address.line1,
                        "line2": address.line2, "city": address.city, "state": address.state,
                        "pincode": address.pincode})
    return initial


@require_POST
def coupon_apply(request):
    """Remember the typed code in the session. Eligibility and the discount are recalculated on the server at checkout."""
    code = request.POST.get("coupon_code", "").strip().upper()
    if not code:
        messages.error(request, "Enter a coupon code.")
        return redirect("store:checkout")
    if len(code) > 40:
        request.session.pop(COUPON_KEY, None)
        messages.error(request, "Coupon codes cannot exceed 40 characters.")
        return redirect("store:checkout")
    try:
        quote_coupon(get_cart(request, create=False), code)
    except ValidationError as error:
        request.session.pop(COUPON_KEY, None)
        messages.error(request, " ".join(error.messages))
    else:
        request.session[COUPON_KEY] = code
        messages.success(request, f"Coupon {code} applied.")
    return redirect("store:checkout")


@require_POST
def coupon_remove(request):
    request.session.pop(COUPON_KEY, None)
    messages.info(request, "Coupon removed.")
    return redirect("store:checkout")


def _coupon_state(request, cart, summary):
    """Return (code, discount, totals). A coupon that is no longer valid is dropped with a message."""
    code, discount = request.session.get(COUPON_KEY, ""), Decimal("0.00")
    if code:
        try:
            _, discount = quote_coupon(cart, code)
        except ValidationError as error:
            request.session.pop(COUPON_KEY, None)
            messages.error(request, " ".join(error.messages))
            code = ""
    shipping = shipping_fee_for(summary["subtotal"])
    return code, discount, {"subtotal": summary["subtotal"], "discount": discount, "shipping": shipping,
                            "total": summary["subtotal"] - discount + shipping}


def _resume_order(request, order):
    request.session.pop(CHECKOUT_TOKEN_KEY, None)
    request.session.pop(COUPON_KEY, None)
    if not request.user.is_authenticated and order.user_id is None:
        recent = request.session.get(RECENT_ORDERS_KEY, [])
        request.session[RECENT_ORDERS_KEY] = (recent + [order.number])[-5:]
    if order.payment_method == "razorpay" and order.payment_status != Order.PaymentStatus.PAID:
        return redirect("store:payment_page", number=order.number)
    return redirect("store:order_success", number=order.number)


def checkout(request):
    cart = get_cart(request, create=False)
    summary = cart_summary(cart)
    if not summary["lines"]:
        messages.info(request, "Your cart is empty.")
        return redirect("store:cart")
    coupon_code, discount, totals = _coupon_state(request, cart, summary)
    site = SiteSettings.load()
    payment_choices = (["cod"] if site.cod_enabled else []) + (["razorpay"] if is_configured() else [])
    token = request.session.get(CHECKOUT_TOKEN_KEY)
    if not token:
        token = secrets.token_urlsafe(24)
        request.session[CHECKOUT_TOKEN_KEY] = token
    if request.method == "POST":
        form = CheckoutForm(request.POST, payment_choices=payment_choices)
        if summary["has_issues"]:
            messages.error(request, "Some items in your cart changed. Please review your cart.")
            return redirect("store:cart")
        key = request.POST.get("checkout_token", "")
        existing = Order.objects.filter(idempotency_key=key).first() if key else None
        if existing:
            # A matching idempotency key from this session proves this is a
            # retry of its prior submission. Reuse the order and restore guest
            # session ownership before redirecting.
            owns_existing_order = False
            if request.user.is_authenticated:
                owns_existing_order = existing.user_id == request.user.pk
            else:
                owns_existing_order = existing.user_id is None
            if not owns_existing_order:
                # Do not reveal another customer's order or turn a stale
                # browser submission into an unexplained 404. Rotate only the
                # checkout token; leave the order and cart untouched.
                request.session.pop(CHECKOUT_TOKEN_KEY, None)
                messages.error(
                    request,
                    "This checkout session has expired. Please review checkout and submit again.",
                )
                return redirect("store:checkout")
            return _resume_order(request, existing)

        # Handle saved address selection
        if request.user.is_authenticated:
            address_pk = request.POST.get("use_address")
            if address_pk:
                try:
                    address = Address.objects.get(pk=address_pk, user=request.user)
                    form = CheckoutForm(request.POST, payment_choices=payment_choices)
                    form.data = form.data.copy()
                    form.data["full_name"] = address.full_name
                    form.data["phone"] = address.phone
                    form.data["line1"] = address.line1
                    form.data["line2"] = address.line2 or ""
                    form.data["city"] = address.city
                    form.data["state"] = address.state
                    form.data["pincode"] = address.pincode
                except (Address.DoesNotExist, ValueError):
                    pass

        if form.is_valid() and key == token and payment_choices:
            method = form.cleaned_data["payment_method"]
            try:
                order = create_order(
                    cart=cart, user=request.user, data=form.cleaned_data,
                    idempotency_key=key, payment_method=method, coupon_code=coupon_code
                )
            except ValidationError as error:
                form.add_error(None, " ".join(error.messages))
            except IntegrityError:
                order = Order.objects.filter(idempotency_key=key).first()
                if order is None:
                    raise
                return _resume_order(request, order)
            else:
                return _resume_order(request, order)
        elif key != token:
            messages.error(request, "This checkout session has expired. Please try again.")
            return redirect("store:checkout")
    else:
        form = CheckoutForm(initial=_checkout_initial(request), payment_choices=payment_choices)
    saved_addresses = request.user.addresses.all() if request.user.is_authenticated else []
    return render(request, "store/checkout.html", {
        "form": form, "summary": summary, "checkout_token": token,
        "totals": totals, "coupon_code": coupon_code,
        "payment_available": bool(payment_choices),
        "saved_addresses": saved_addresses,
    })
@never_cache
def payment_page(request, number):
    order = get_object_or_404(Order, number=number)
    is_owner = request.user.is_authenticated and order.user_id == request.user.pk
    is_guest_session = not request.user.is_authenticated and order.user_id is None
    recent_orders = request.session.get(RECENT_ORDERS_KEY, [])
    is_guest_owner = is_guest_session and number in recent_orders
    checkout_token = request.session.get(CHECKOUT_TOKEN_KEY, "")
    is_checkout_owner = (
        is_guest_session
        and bool(order.idempotency_key)
        and bool(checkout_token)
        and secrets.compare_digest(checkout_token, order.idempotency_key)
    )
    if not (is_owner or is_guest_owner or is_checkout_owner):
        raise Http404
    if is_checkout_owner and not is_guest_owner:
        request.session[RECENT_ORDERS_KEY] = (recent_orders + [order.number])[-5:]
    if order.payment_method != "razorpay" or order.payment_status == Order.PaymentStatus.PAID:
        return redirect("store:order_success", number=order.number)
    if order.payment_status == Order.PaymentStatus.REFUNDED:
        messages.error(request, "This order's online payment has been refunded and cannot be retried.")
        return redirect("store:order_success", number=order.number)
    if order.status == Order.Status.CANCELLED:
        messages.error(request, "This order has been cancelled.")
        return redirect("store:order_success", number=order.number)
    if not order.razorpay_order_id:
        try:
            gateway_order = create_gateway_order(order)
            order.razorpay_order_id = gateway_order["id"]
            order.save(update_fields=["razorpay_order_id", "updated_at"])
        except Exception:
            logger.exception("Could not create Razorpay order for %s", order.number)
            messages.error(request, "Online payment could not be started. Please try again later.")
            return redirect("store:order_success", number=order.number)
    return render(request, "store/payment.html", {
        "order": order,
        "razorpay_key": settings.RAZORPAY_KEY_ID,
        "amount_paise": amount_in_paise(order.total),
    })
@never_cache
def order_success(request, number):
    order = get_object_or_404(
        Order.objects.prefetch_related("items").select_related("shipment"),
        number=number,
    )
    is_owner = request.user.is_authenticated and order.user_id == request.user.pk
    if not (is_owner or number in request.session.get(RECENT_ORDERS_KEY, [])):
        raise Http404
    return render(request, "store/order_success.html", {"order": order})



