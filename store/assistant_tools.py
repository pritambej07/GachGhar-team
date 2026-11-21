"""Allowlisted backend tools for the GachGhar AI Gardener.

Rules enforced here (never in the model, never in the browser):
- The model can only call tools listed in TOOLS. Unknown names are rejected.
- Identity comes from the Django request, never from tool arguments.
- Prices, stock, totals and ownership are read from the database on every call.
- Cart and wishlist changes are staged with a server-side pending action; only a customer confirmation button
  executes them through the normal, validated service functions.
- Consequential actions (cancelling an order) are never executed by a tool. A tool only *requests* them;
  the customer must press a confirmation button, which calls confirm_pending_action().
- Placing orders and payments are not available as tools. The assistant links to the normal secure checkout.
- Tool results contain no email, phone or address, so private contact data is never sent to the AI provider.
"""
import operator
import re
import secrets
import time
from decimal import Decimal, InvalidOperation
from functools import reduce

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.urls import reverse

from .formatting import format_inr
from .models import (Category, Guide, Order, Product, ProductVariant, SiteSettings, StaticPage, WishlistItem)
from .payments import is_configured
from .services import (add_to_cart, cart_summary, get_cart, set_cart_quantity, shipping_fee_for,
                       quote_coupon, transition_order, visible_products)

MAX_RESULTS = 6
PENDING_KEY = "assistant_pending_action"
PENDING_TTL_SECONDS = 600
CONFIRMATION_REQUIRED_TOOLS = {"add_to_cart", "update_cart_quantity", "remove_from_cart",
                               "wishlist_add", "wishlist_remove"}


# ---------- helpers ----------

def _ok(**data):
    return {"ok": True, **data}


def _fail(error, **data):
    return {"ok": False, "error": error, **data}


def _int(value, name, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a whole number.")
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise ValidationError(f"{name} is out of range.")
    return number


def _money(value):
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError("Price must be a number.")
    if not number.is_finite() or number < 0:
        raise ValidationError("Price must be a positive number.")
    return number


def _variant_dict(variant):
    return {"variant_id": variant.pk, "name": variant.name, "price": format_inr(variant.price),
            "price_value": str(variant.price), "in_stock": variant.stock > 0, "stock": variant.stock,
            "low_stock": 0 < variant.stock <= variant.low_stock_threshold}


def _product_dict(product, detail=False):
    variants = [v for v in product.variants.all() if v.is_active]
    variants.sort(key=lambda v: (v.sort_order, v.price))
    images = list(product.images.all())
    data = {
        "product_id": product.pk, "name": product.name, "category": product.category.name,
        "url": product.get_absolute_url(), "image_url": images[0].image.url if images else "",
        "from_price": format_inr(min(v.price for v in variants)) if variants else "",
        "in_stock": any(v.stock > 0 for v in variants),
        "variants": [_variant_dict(v) for v in variants],
    }
    if detail:
        data.update({
            "description": product.description[:800], "highlights": product.highlights[:500],
            "specifications": product.specifications[:600], "care_instructions": product.care_instructions[:1000],
        })
    return data


def _login_required():
    return _fail("login_required", message="Please log in to use this. Your cart is unaffected.",
                 login_url=reverse("accounts:login"))


def _order_owned(request, number):
    """Return the order only if it belongs to the signed-in customer."""
    if not request.user.is_authenticated:
        return None
    return (Order.objects.filter(number=str(number).strip()[:24], user=request.user)
            .prefetch_related("items", "events").first())


# ---------- catalogue tools ----------

def search_products(request, query="", category="", min_price=None, max_price=None, in_stock_only=False, limit=MAX_RESULTS):
    try:
        low, high = _money(min_price), _money(max_price)
        limit = _int(limit, "limit", 1, MAX_RESULTS)
    except ValidationError as error:
        return _fail("invalid_input", message=" ".join(error.messages))
    qs = visible_products().prefetch_related("variants")
    words = [w for w in re.findall(r"[\w\u0980-\u09FF]{2,}", str(query).lower())][:6]
    if words:
        qs = qs.filter(reduce(operator.or_, [
            Q(name__icontains=w) | Q(description__icontains=w) | Q(highlights__icontains=w) |
            Q(specifications__icontains=w) | Q(care_instructions__icontains=w) | Q(category__name__icontains=w)
            for w in words]))
    if category:
        cat = Category.objects.filter(is_active=True).filter(
            Q(slug=str(category).strip().lower()) | Q(name__iexact=str(category).strip())).first()
        if cat is None:
            return _fail("category_not_found", message="That category does not exist.",
                         categories=list(Category.objects.filter(is_active=True).values_list("name", flat=True)[:30]))
        qs = qs.filter(category_id__in=cat.descendant_ids())
    if low is not None:
        qs = qs.filter(min_price__gte=low)
    if high is not None:
        qs = qs.filter(min_price__lte=high)
    if in_stock_only:
        qs = qs.filter(total_stock__gt=0)
    products = list(qs.order_by("-is_featured", "min_price", "id")[:limit])
    return _ok(count=len(products), products=[_product_dict(p) for p in products],
               note="" if products else "No active products matched. The catalogue may not stock this yet.")


def list_categories(request):
    cats = Category.objects.filter(is_active=True).order_by("sort_order", "name")
    return _ok(categories=[{"name": c.name, "slug": c.slug, "url": c.get_absolute_url(),
                            "is_top_level": c.parent_id is None} for c in cats[:40]])


def get_product(request, product_id):
    try:
        pk = _int(product_id, "product_id", 1)
    except ValidationError as error:
        return _fail("invalid_input", message=" ".join(error.messages))
    product = (Product.objects.filter(pk=pk, is_active=True).select_related("category")
               .prefetch_related("variants", "images").first())
    if product is None or not any(v.is_active for v in product.variants.all()):
        return _fail("not_found", message="That product is not available.")
    return _ok(product=_product_dict(product, detail=True))


def compare_products(request, product_ids):
    if not isinstance(product_ids, (list, tuple)) or not 2 <= len(product_ids) <= 4:
        return _fail("invalid_input", message="Choose between 2 and 4 products to compare.")
    try:
        ids = [_int(i, "product_id", 1) for i in product_ids]
    except ValidationError as error:
        return _fail("invalid_input", message=" ".join(error.messages))
    products = (Product.objects.filter(pk__in=ids, is_active=True).select_related("category")
                .prefetch_related("variants", "images"))
    found = [_product_dict(p, detail=True) for p in products if any(v.is_active for v in p.variants.all())]
    if len(found) < 2:
        return _fail("not_found", message="Fewer than two of those products are available to compare.")
    return _ok(products=found)


def search_guides(request, query):
    words = [w for w in re.findall(r"[\w\u0980-\u09FF]{3,}", str(query).lower())][:5]
    qs = Guide.objects.filter(is_published=True)
    if words:
        qs = qs.filter(reduce(operator.or_, [Q(title__icontains=w) | Q(summary__icontains=w) | Q(body__icontains=w)
                                             for w in words]))
    guides = list(qs[:3])
    return _ok(guides=[{"title": g.title, "url": g.get_absolute_url(), "summary": g.summary,
                        "excerpt": g.body[:600]} for g in guides],
               note="" if guides else "No published GachGhar guide matched.")


def get_page_link(request, target, slug=""):
    fixed = {"home": "store:home", "products": "store:products", "cart": "store:cart", "checkout": "store:checkout",
             "wishlist": "store:wishlist", "orders": "accounts:orders", "guides": "store:guides",
             "login": "accounts:login", "register": "accounts:register",
             "password_reset": "accounts:password_reset", "profile": "accounts:profile",
             "password_change": "accounts:password_change"}
    if target == "category":
        cat = Category.objects.filter(slug=str(slug).strip().lower(), is_active=True).first()
        if cat is None:
            return _fail("not_found", message="That category does not exist.")
        return _ok(label=cat.name, url=cat.get_absolute_url())
    if target in {"about", "contact", "returns", "shipping", "privacy", "terms"}:
        page = StaticPage.objects.filter(slug=target, is_published=True).first()
        if page:
            return _ok(label=page.title, url=page.get_absolute_url())
        if target == "returns":
            contact = StaticPage.objects.filter(slug="contact", is_published=True).first()
            if contact:
                return _ok(label=contact.title, url=contact.get_absolute_url(),
                           message="No returns policy is currently published. Please contact GachGhar.")
        return _fail("not_found", message="That support page is not currently published.")
    if target not in fixed:
        return _fail("invalid_input", message="Unknown page.",
                     allowed=sorted(list(fixed) + ["about", "category", "contact", "privacy", "returns", "shipping", "terms"]))
    if target in ("wishlist", "orders", "profile", "password_change") and not request.user.is_authenticated:
        return _login_required()
    return _ok(label=target.title(), url=reverse(fixed[target]))


# ---------- cart tools ----------

def _cart_result(request):
    summary = cart_summary(get_cart(request, create=False))
    return {
        "count": summary["count"], "subtotal": format_inr(summary["subtotal"]),
        "shipping": format_inr(summary["shipping"]), "total": format_inr(summary["total"]),
        "has_issues": summary["has_issues"], "cart_url": reverse("store:cart"),
        "lines": [{"variant_id": l["variant_id"], "product": l["product_name"], "option": l["variant_name"],
                   "quantity": l["quantity"], "unit_price": format_inr(l["unit_price"]),
                   "line_total": format_inr(l["line_total"]), "in_stock": l["in_stock"], "url": l["url"],
                   "image_url": l["image_url"]} for l in summary["lines"]],
    }


def get_cart_tool(request):
    return _ok(cart=_cart_result(request))


def add_to_cart_tool(request, variant_id, quantity=1):
    try:
        vid = _int(variant_id, "variant_id", 1)
        qty = _int(quantity, "quantity", 1)
    except ValidationError as error:
        return _fail("invalid_input", message=" ".join(error.messages))
    try:
        item = add_to_cart(get_cart(request), vid, qty)
    except ValidationError as error:
        return _fail("rejected", message=" ".join(error.messages), cart=_cart_result(request))
    except ProductVariant.DoesNotExist:
        return _fail("not_found", message="That product option does not exist.")
    return _ok(message=f"Added {qty} × {item.variant.product.name} ({item.variant.name}) to your cart. "
                       f"Cart now has {item.quantity} of this item.", cart=_cart_result(request), mutated="cart")


def _own_cart_item(request, variant_id):
    cart = get_cart(request, create=False)
    if cart is None:
        return None
    return cart.items.filter(variant_id=variant_id).select_related("variant__product").first()


def update_cart_quantity_tool(request, variant_id, quantity):
    try:
        vid = _int(variant_id, "variant_id", 1)
        qty = _int(quantity, "quantity", 0)
    except ValidationError as error:
        return _fail("invalid_input", message=" ".join(error.messages))
    item = _own_cart_item(request, vid)
    if item is None:
        return _fail("not_in_cart", message="That item is not in your cart.", cart=_cart_result(request))
    name = f"{item.variant.product.name} ({item.variant.name})"
    try:
        set_cart_quantity(item, qty)
    except ValidationError as error:
        return _fail("rejected", message=" ".join(error.messages), cart=_cart_result(request))
    message = f"Removed {name} from your cart." if qty == 0 else f"Set {name} to quantity {qty}."
    return _ok(message=message, cart=_cart_result(request), mutated="cart")


def remove_from_cart_tool(request, variant_id):
    return update_cart_quantity_tool(request, variant_id, 0)


# ---------- wishlist tools ----------

def wishlist_list(request):
    if not request.user.is_authenticated:
        return _login_required()
    products = (visible_products().filter(wishlisted_by__user=request.user).prefetch_related("variants")[:20])
    return _ok(products=[_product_dict(p) for p in products])


def wishlist_add(request, product_id):
    if not request.user.is_authenticated:
        return _login_required()
    try:
        pk = _int(product_id, "product_id", 1)
    except ValidationError as error:
        return _fail("invalid_input", message=" ".join(error.messages))
    product = Product.objects.filter(pk=pk, is_active=True).first()
    if product is None:
        return _fail("not_found", message="That product is not available.")
    _, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
    return _ok(message=f"Saved {product.name} to your wishlist." if created
               else f"{product.name} was already in your wishlist.", mutated="wishlist")


def wishlist_remove(request, product_id):
    if not request.user.is_authenticated:
        return _login_required()
    try:
        pk = _int(product_id, "product_id", 1)
    except ValidationError as error:
        return _fail("invalid_input", message=" ".join(error.messages))
    entry = WishlistItem.objects.filter(user=request.user, product_id=pk).select_related("product").first()
    if entry is None:
        return _fail("not_in_wishlist", message="That product is not in your wishlist.")
    name = entry.product.name
    entry.delete()
    return _ok(message=f"Removed {name} from your wishlist.", mutated="wishlist")


# ---------- order tools (owner only) ----------

def _order_dict(order, detail=False):
    data = {"order_number": order.number, "status": order.get_status_display(),
            "payment_method": order.payment_method, "payment_status": order.get_payment_status_display(),
            "total": format_inr(order.total), "placed_on": order.created_at.strftime("%d %b %Y"),
            "url": order.get_absolute_url(), "can_cancel": order.can_cancel}
    if detail:
        data["invoice_url"] = reverse("accounts:order_invoice", args=[order.number])
        data["items"] = [{"product": i.product_name, "option": i.variant_name, "quantity": i.quantity,
                          "line_total": format_inr(i.line_total)} for i in order.items.all()]
        shipment = getattr(order, "shipment", None)
        data["shipment"] = ({"courier": shipment.carrier, "tracking_number": shipment.tracking_number,
                             "tracking_url": shipment.tracking_url, "status": shipment.get_status_display()}
                            if shipment else None)
        if shipment is None:
            data["shipment_note"] = "No courier shipment has been recorded for this order yet."
    return data


def list_my_orders(request):
    if not request.user.is_authenticated:
        return _login_required()
    orders = Order.objects.filter(user=request.user)[:5]
    return _ok(orders=[_order_dict(o) for o in orders], note="" if orders else "You have no orders yet.")


def get_order_status(request, order_number):
    if not request.user.is_authenticated:
        return _login_required()
    order = _order_owned(request, order_number)
    if order is None:  # same answer for "does not exist" and "belongs to someone else"
        return _fail("not_found", message="I could not find that order on your account.")
    return _ok(order=_order_dict(order, detail=True))


def get_checkout_info(request):
    site = SiteSettings.load()
    summary = cart_summary(get_cart(request, create=False))
    methods = []
    if site.cod_enabled:
        methods.append("Cash on Delivery")
    if is_configured():
        methods.append("Razorpay")
    return _ok(
        payment_methods=methods or ["No payment method is enabled right now."],
        shipping_fee=format_inr(site.shipping_fee),
        free_shipping_above=(format_inr(site.free_shipping_threshold)
                             if site.free_shipping_threshold is not None else None),
        current_shipping=format_inr(shipping_fee_for(summary["subtotal"])), cart_total=format_inr(summary["total"]),
        checkout_url=reverse("store:checkout"),
        note="Orders and payments are completed on the secure checkout page. The assistant cannot place orders or pay.")


def get_coupon_info(request, code):
    if not isinstance(code, str) or not code.strip() or len(code) > 40:
        return _fail("invalid_input", message="Enter a valid coupon code to check it.")
    try:
        coupon, discount = quote_coupon(get_cart(request, create=False), code)
    except ValidationError as error:
        return _fail("coupon_unavailable", message=" ".join(error.messages),
                     checkout_url=reverse("store:checkout"))
    return _ok(
        coupon={"code": coupon.code, "description": coupon.description,
                "discount_type": coupon.get_discount_type_display(),
                "discount": format_inr(discount), "minimum_order": format_inr(coupon.min_order_value)},
        checkout_url=reverse("store:checkout"),
        message="This coupon is valid for the current cart. The discount is recalculated at checkout.",
    )


# ---------- consequential action: cancellation needs customer confirmation ----------

def request_order_cancellation(request, order_number):
    """Prepare a cancellation. Nothing is cancelled until the customer confirms with the button."""
    if not request.user.is_authenticated:
        return _login_required()
    if _has_live_pending_action(request):
        return _fail("confirmation_pending", message="Please confirm or decline the pending action first.")
    order = _order_owned(request, order_number)
    if order is None:
        return _fail("not_found", message="I could not find that order on your account.")
    if not order.can_cancel:
        return _fail("not_allowed", message=f"Order {order.number} is {order.get_status_display().lower()} "
                                            "and can no longer be cancelled online.")
    token = secrets.token_urlsafe(16)
    request.session[PENDING_KEY] = {"token": token, "action": "cancel_order", "order_number": order.number,
                                    "user_id": request.user.pk, "expires": time.time() + PENDING_TTL_SECONDS}
    return _ok(awaiting_confirmation=True,
               confirmation={"token": token, "action": "cancel_order", "order_number": order.number,
                             "prompt": f"Cancel order {order.number} ({format_inr(order.total)})? This cannot be undone."},
               message="Cancellation is NOT done yet. The customer must press the Confirm button shown on screen.")


def _has_live_pending_action(request):
    pending = request.session.get(PENDING_KEY)
    if not pending:
        return False
    try:
        is_live = time.time() <= float(pending.get("expires", 0))
    except (AttributeError, TypeError, ValueError):
        is_live = False
    if not is_live:
        request.session.pop(PENDING_KEY, None)
    return is_live


def prepare_user_action(request, name, arguments):
    """Prepare a cart/wishlist mutation for an explicit customer confirmation; do not mutate here."""
    if name not in CONFIRMATION_REQUIRED_TOOLS:
        return _fail("invalid_action", message="That action cannot be prepared for confirmation.")
    if _has_live_pending_action(request):
        return _fail("confirmation_pending", message="Please confirm or decline the pending action first.")
    if not isinstance(arguments, dict):
        return _fail("invalid_input", message="Arguments must be an object.")
    _, _, schema = TOOLS[name]
    allowed = set(schema["properties"])
    clean = {key: value for key, value in arguments.items() if key in allowed}
    if any(key not in clean for key in schema["required"]):
        return _fail("invalid_input", message="Missing or invalid arguments.")

    try:
        if name == "add_to_cart":
            variant_id = _int(clean["variant_id"], "variant_id", 1)
            quantity = _int(clean.get("quantity", 1), "quantity", 1)
            variant = (ProductVariant.objects.select_related("product")
                       .filter(pk=variant_id, is_active=True, product__is_active=True).first())
            if variant is None:
                return _fail("not_found", message="That product option is not available.")
            if quantity > variant.stock:
                return _fail("rejected", message=f"Only {variant.stock} of {variant.product.name} are in stock.")
            item = _own_cart_item(request, variant_id)
            if item and item.quantity + quantity > variant.stock:
                return _fail("rejected", message=f"Only {variant.stock} of {variant.product.name} are in stock.")
            clean = {"variant_id": variant_id, "quantity": quantity}
            prompt = (f"Add {quantity} × {variant.product.name} ({variant.name}) to your cart?")
        elif name in ("update_cart_quantity", "remove_from_cart"):
            variant_id = _int(clean["variant_id"], "variant_id", 1)
            quantity = 0 if name == "remove_from_cart" else _int(clean["quantity"], "quantity", 0)
            item = _own_cart_item(request, variant_id)
            if item is None:
                return _fail("not_in_cart", message="That item is not in your cart.")
            clean = {"variant_id": variant_id, "quantity": quantity}
            label = f"{item.variant.product.name} ({item.variant.name})"
            prompt = (f"Remove {label} from your cart?" if quantity == 0
                      else f"Change {label} quantity from {item.quantity} to {quantity}?")
        elif name in ("wishlist_add", "wishlist_remove"):
            if not request.user.is_authenticated:
                return _login_required()
            product_id = _int(clean["product_id"], "product_id", 1)
            product = Product.objects.filter(pk=product_id, is_active=True).first()
            if product is None:
                return _fail("not_found", message="That product is not available.")
            entry = WishlistItem.objects.filter(user=request.user, product=product).first()
            if name == "wishlist_add":
                if entry:
                    return _ok(message=f"{product.name} is already in your wishlist.")
                prompt = f"Add {product.name} to your wishlist?"
            else:
                if entry is None:
                    return _fail("not_in_wishlist", message="That product is not in your wishlist.")
                prompt = f"Remove {product.name} from your wishlist?"
            clean = {"product_id": product_id}
    except ValidationError as error:
        return _fail("invalid_input", message=" ".join(error.messages))

    token = secrets.token_urlsafe(16)
    request.session[PENDING_KEY] = {
        "token": token, "action": name, "arguments": clean,
        "user_id": request.user.pk if request.user.is_authenticated else None,
        "expires": time.time() + PENDING_TTL_SECONDS,
    }
    return _ok(
        awaiting_confirmation=True,
        confirmation={"token": token, "action": name, "prompt": prompt},
        message="Nothing has changed yet. The customer must confirm this action.",
    )


def confirm_pending_action(request, token, decision):
    """Called only by the confirmation endpoint (a button press), never by the AI model."""
    pending = request.session.get(PENDING_KEY)
    if not pending or not secrets.compare_digest(str(pending.get("token", "")), str(token or "")):
        return _fail("no_pending_action", message="There is nothing waiting for confirmation.")
    request.session.pop(PENDING_KEY, None)  # one use only
    current_user_id = request.user.pk if request.user.is_authenticated else None
    if pending.get("user_id") != current_user_id:
        return _fail("login_required", message="Please log in again to confirm.")
    if time.time() > pending["expires"]:
        return _fail("expired", message="That confirmation expired. Please ask again.")
    if decision != "confirm":
        if pending.get("action") == "cancel_order":
            return _ok(message="Okay, I did not cancel anything.", cancelled_request=True)
        return _ok(message="Okay, I did not make that change.")
    action = pending.get("action")
    if action in CONFIRMATION_REQUIRED_TOOLS:
        result = run_tool(request, action, pending.get("arguments"))
        if result.get("ok"):
            result["_audit"] = {"tool": action, "arguments": pending["arguments"]}
        return result
    if action != "cancel_order" or not request.user.is_authenticated:
        return _fail("invalid_pending_action", message="That confirmation is no longer valid.")
    order = _order_owned(request, pending["order_number"])
    if order is None:
        return _fail("not_found", message="I could not find that order on your account.")
    try:
        transition_order(order, Order.Status.CANCELLED, actor=request.user, note="Cancelled by customer via AI Gardener (confirmed).")
    except ValidationError as error:
        return _fail("not_allowed", message=" ".join(error.messages))
    return _ok(message=f"Order {order.number} has been cancelled and its stock released.", mutated="order")


# ---------- registry ----------

def _obj(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


TOOLS = {
    "search_products": (search_products, "Search active products by keywords (name, description, care, category), category, price range and stock. Use for finding or recommending plants.",
                        _obj({"query": {"type": "string"}, "category": {"type": "string", "description": "category name or slug"},
                              "min_price": {"type": "number"}, "max_price": {"type": "number"},
                              "in_stock_only": {"type": "boolean"}, "limit": {"type": "integer"}})),
    "list_categories": (list_categories, "List the store's active categories.", _obj({})),
    "get_product": (get_product, "Get full details, care notes, variants, prices and stock of one product.",
                    _obj({"product_id": {"type": "integer"}}, ["product_id"])),
    "compare_products": (compare_products, "Compare 2 to 4 products using real catalogue data.",
                         _obj({"product_ids": {"type": "array", "items": {"type": "integer"}}}, ["product_ids"])),
    "search_guides": (search_guides, "Find published GachGhar plant-care guides.", _obj({"query": {"type": "string"}}, ["query"])),
    "get_page_link": (get_page_link, "Get the correct store page link. target: home, products, category, cart, checkout, wishlist, orders, guides.",
                      _obj({"target": {"type": "string"}, "slug": {"type": "string"}}, ["target"])),
    "get_cart": (get_cart_tool, "Show the current cart with accurate totals.", _obj({})),
    "add_to_cart": (add_to_cart_tool, "Propose adding a product option (variant_id from search results) to the cart. The customer must confirm before it changes.",
                    _obj({"variant_id": {"type": "integer"}, "quantity": {"type": "integer"}}, ["variant_id"])),
    "update_cart_quantity": (update_cart_quantity_tool, "Propose changing a cart line quantity. The customer must confirm before it changes.",
                             _obj({"variant_id": {"type": "integer"}, "quantity": {"type": "integer"}}, ["variant_id", "quantity"])),
    "remove_from_cart": (remove_from_cart_tool, "Propose removing a cart line. The customer must confirm before it changes.",
                         _obj({"variant_id": {"type": "integer"}}, ["variant_id"])),
    "wishlist_list": (wishlist_list, "List the signed-in customer's wishlist.", _obj({})),
    "wishlist_add": (wishlist_add, "Propose adding a product to the signed-in customer's wishlist. The customer must confirm.",
                     _obj({"product_id": {"type": "integer"}}, ["product_id"])),
    "wishlist_remove": (wishlist_remove, "Propose removing a product from the signed-in customer's wishlist. The customer must confirm.",
                        _obj({"product_id": {"type": "integer"}}, ["product_id"])),
    "list_my_orders": (list_my_orders, "List the signed-in customer's recent orders.", _obj({})),
    "get_order_status": (get_order_status, "Get status, payment and real shipment/tracking info of the signed-in customer's own order.",
                         _obj({"order_number": {"type": "string"}}, ["order_number"])),
    "get_checkout_info": (get_checkout_info, "Explain checkout, shipping fee and available payment methods.", _obj({})),
    "get_coupon_info": (get_coupon_info, "Check a customer-provided coupon code against the current cart. Never invent codes.",
                        _obj({"code": {"type": "string"}}, ["code"])),
    "request_order_cancellation": (request_order_cancellation,
                                   "Ask to cancel the customer's own order. This only prepares a confirmation button; the customer must confirm. Never claim it is cancelled.",
                                   _obj({"order_number": {"type": "string"}}, ["order_number"])),
}


def tool_specs():
    return [{"name": name, "description": desc, "parameters": schema} for name, (_, desc, schema) in TOOLS.items()]


def run_tool(request, name, arguments):
    """Execute one allowlisted tool. Arguments are filtered to the declared schema; errors never leak internals."""
    entry = TOOLS.get(name)
    if entry is None:
        return _fail("unknown_tool", message="That action is not available.")
    func, _, schema = entry
    if not isinstance(arguments, dict):
        return _fail("invalid_input", message="Arguments must be an object.")
    allowed = set(schema["properties"])
    clean = {k: v for k, v in arguments.items() if k in allowed}
    try:
        return func(request, **clean)
    except TypeError:
        return _fail("invalid_input", message="Missing or invalid arguments.")
    except Exception:  # noqa: BLE001 - tool failures must never crash the chat or expose internals
        import logging
        logging.getLogger("store.assistant").exception("assistant tool %s failed", name)
        return _fail("tool_error", message="That action failed. Nothing was changed.")
