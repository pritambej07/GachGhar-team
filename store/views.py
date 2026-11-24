import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.core.validators import validate_email
from django.core.mail import send_mail
from django.db import connection
from django.db.models import Avg, Q
from django.http import Http404, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import ai_services
from .forms import ContactForm, ReviewForm
from .models import (Category, Guide, HomeSection, NewsletterSubscriber, Product, Review, StaticPage,
                     WishlistItem, BlogPost, SiteSettings)
from .services import visible_products

PAGE_SIZE = 12
RECENT_PRODUCTS_KEY = "recent_products"
SORTS = {
    "recommended": ("-is_featured", "-created_at"),
    "price_asc": ("min_price", "name"),
    "price_desc": ("-min_price", "name"),
    "newest": ("-created_at",),
}
SORT_LABELS = {"recommended": "Recommended", "price_asc": "Price: low to high",
               "price_desc": "Price: high to low", "newest": "Newest"}
MAX_FILTER_PRICE = Decimal("99999999.99")
MAX_FILTER_PRICE_LENGTH = 16

STATIC_PAGE_FALLBACKS = {
    "about": {
        "title": "About GachGhar",
        "body": (
            "GachGhar is for people who find joy in growing plants and bringing nature into everyday spaces. "
            "We want gardening to feel approachable, whether you are caring for your first pot or tending a garden."
        ),
    },
    "contact": {
        "title": "Contact GachGhar",
        "body": (
            "We are here to help with your GachGhar experience. For an existing order, sign in to your account "
            "and visit My Orders. For product, plant-care, or general questions, send us a message below."
        ),
    },
}


def _finite_decimal(value):
    if not isinstance(value, str) or len(value) > MAX_FILTER_PRICE_LENGTH:
        return None
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() and 0 <= number <= MAX_FILTER_PRICE else None


def _listing(request, base_qs, *, title, description="", category=None):
    qs = base_qs
    query = request.GET.get("q", "").strip()[:100]
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(description__icontains=query))
    raw_min_price = request.GET.get("min_price", "")
    raw_max_price = request.GET.get("max_price", "")
    min_price = _finite_decimal(raw_min_price)
    max_price = _finite_decimal(raw_max_price)
    if min_price is not None:
        qs = qs.filter(min_price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(min_price__lte=max_price)
    in_stock = request.GET.get("in_stock") == "1"
    if in_stock:
        qs = qs.filter(total_stock__gt=0)
    sort = request.GET.get("sort") if request.GET.get("sort") in SORTS else "recommended"
    paginator = Paginator(qs.order_by(*SORTS[sort], "id"), PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    normalized_query = QueryDict("", mutable=True)
    if query:
        normalized_query["q"] = query
    if min_price is not None:
        normalized_query["min_price"] = format(min_price, "f")
    if max_price is not None:
        normalized_query["max_price"] = format(max_price, "f")
    if in_stock:
        normalized_query["in_stock"] = "1"
    if sort in SORTS and request.GET.get("sort") in SORTS:
        normalized_query["sort"] = sort
    request.GET = normalized_query
    return render(request, "store/product_list.html", {
        "page": page, "title": title, "description": description, "category": category,
        "subcategories": category.children.filter(is_active=True) if category else [],
        "q": query, "sort": sort, "sort_labels": SORT_LABELS, "in_stock": in_stock,
        "min_price": format(min_price, "f") if min_price is not None else "",
        "max_price": format(max_price, "f") if max_price is not None else "",
        "total_count": paginator.count,
    })


def home(request):
    sections = []
    kinds = set()
    for section in HomeSection.objects.filter(enabled=True).select_related("category"):
        kinds.add(section.kind)
        block = {"kind": section.kind, "title": section.title or section.get_kind_display(), "category": section.category}
        if section.kind == HomeSection.Kind.FEATURED:
            block["products"] = visible_products().filter(is_featured=True)[:8]
        elif section.kind == HomeSection.Kind.CATEGORY_PRODUCTS:
            if not section.category_id:
                continue
            block["products"] = visible_products().filter(category_id__in=section.category.descendant_ids())[:8]
        elif section.kind == HomeSection.Kind.CATEGORIES:
            block["categories"] = Category.objects.filter(is_active=True, parent__isnull=True)
        elif section.kind == HomeSection.Kind.GUIDES:
            block["guides"] = Guide.objects.filter(is_published=True)[:3]
        elif section.kind == HomeSection.Kind.REVIEWS:
            block["reviews"] = section_reviews()
        if block.get("products") is not None and not block["products"]:
            continue
        if block.get("categories") is not None and not block["categories"]:
            continue
        if block.get("guides") is not None and not block["guides"]:
            continue
        if block.get("reviews") is not None and not block["reviews"]:
            continue
        sections.append(block)

    active_categories = Category.objects.filter(is_active=True, parent__isnull=True)
    active_products = visible_products()
    if "categories" not in kinds and active_categories.exists():
        sections.insert(0, {
            "kind": "categories",
            "title": "Shop by category",
            "categories": active_categories,
        })
    if "featured" not in kinds and "category_products" not in kinds and active_products.exists():
        featured_products = active_products.filter(is_featured=True)
        sections.append({
            "kind": "featured",
            "title": "Featured plants and essentials",
            "products": featured_products[:8] if featured_products.exists() else active_products[:8],
        })
    return render(request, "store/home.html", {"sections": sections})


def section_reviews():
    return Review.objects.filter(is_approved=True).select_related("product")[:4]


def products(request):
    return _listing(request, visible_products(), title="All products")


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    base = visible_products().filter(category_id__in=category.descendant_ids())
    return _listing(request, base, title=category.name, description=category.description, category=category)


def search(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return render(request, "store/search.html", {"query": ""})

    qs = visible_products().filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(category__name__icontains=query))
    paginator = Paginator(qs.order_by("name", "id"), PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "store/search_results.html", {
        "page": page, "title": "Search results", "q": query, "total_count": paginator.count
    })


def search_suggestions(request):
    """AJAX endpoint for live search suggestions."""
    query = request.GET.get("q", "").strip()

    if not query or len(query) < 2:
        return JsonResponse({"suggestions": []})

    # Search in products - name, description, category
    products = visible_products().filter(
        Q(name__icontains=query) |
        Q(description__icontains=query) |
        Q(category__name__icontains=query)
    )[:8]  # Limit to 8 suggestions

    suggestions = []
    for product in products:
        default_variant = product.variants.filter(is_active=True, stock__gt=0).first() or product.variants.first()
        if default_variant:
            image_url = product.images.first().image.url if product.images.exists() else None
            suggestions.append({
                "name": product.name,
                "url": product.get_absolute_url(),
                "price": str(default_variant.price),
                "image_url": image_url,
                "in_stock": default_variant.stock > 0,
            })

    return JsonResponse({"suggestions": suggestions})


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.filter(is_active=True).select_related("category")
                                .prefetch_related("images"), slug=slug)
    variants = list(product.variants.filter(is_active=True).order_by("sort_order", "price"))
    if not variants:
        raise Http404("Product is not available.")
    approved = product.reviews.filter(is_approved=True)
    rating = approved.aggregate(avg=Avg("rating"))["avg"]
    related = visible_products().filter(category_id=product.category_id).exclude(pk=product.pk)[:4]
    recent_ids = [pk for pk in request.session.get(RECENT_PRODUCTS_KEY, []) if pk != product.pk]
    recent = sorted(visible_products().filter(pk__in=recent_ids[:6]), key=lambda p: recent_ids.index(p.pk))
    request.session[RECENT_PRODUCTS_KEY] = [product.pk] + recent_ids[:5]
    in_wishlist = request.user.is_authenticated and WishlistItem.objects.filter(
        user=request.user, product=product).exists()
    default_variant = next((v for v in variants if v.stock > 0), variants[0])
    review_count = approved.count()
    average = round(rating, 1) if rating else None
    jsonld = {
        "@context": "https://schema.org", "@type": "Product", "name": product.name,
        "description": product.description[:300], "sku": default_variant.sku,
        "offers": {
            "@type": "AggregateOffer", "priceCurrency": "INR", "offerCount": len(variants),
            "lowPrice": str(min(v.price for v in variants)), "highPrice": str(max(v.price for v in variants)),
            "availability": "https://schema.org/InStock" if any(v.stock > 0 for v in variants)
            else "https://schema.org/OutOfStock",
        },
    }
    if review_count:
        jsonld["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": average, "reviewCount": review_count}
    own_review = (Review.objects.filter(product=product, user=request.user).first()
                  if request.user.is_authenticated else None)
    return render(request, "store/product_detail.html", {
        "own_review": own_review,
        "review_form": ReviewForm(initial={"rating": own_review.rating, "title": own_review.title,
                                           "body": own_review.body} if own_review else None),
        "product": product, "variants": variants, "default_variant": default_variant,
        "images": product.images.all(), "reviews": approved.select_related("user")[:10],
        "review_count": review_count, "average_rating": average, "related": related,
        "recent": recent, "in_wishlist": in_wishlist, "jsonld": jsonld,
    })


@login_required
@require_POST
def review_submit(request, slug):
    """Create or update the signed-in customer's single review. Every submission starts as pending moderation."""
    product = get_object_or_404(Product, slug=slug, is_active=True)
    form = ReviewForm(request.POST)
    if not form.is_valid():
        from django.contrib import messages
        messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
        return redirect(f"{product.get_absolute_url()}#write-review")
    review, created = Review.objects.get_or_create(
        product=product, user=request.user,
        defaults={"rating": form.cleaned_data["rating"], "title": form.cleaned_data["title"],
                  "body": form.cleaned_data["body"], "is_approved": False})
    if not created:  # editing resets approval so changed text is moderated again
        review.rating, review.title, review.body = (form.cleaned_data["rating"], form.cleaned_data["title"],
                                                    form.cleaned_data["body"])
        review.is_approved = False
        review.save(update_fields=["rating", "title", "body", "is_approved"])
    from django.contrib import messages
    messages.success(request, "Thank you. Your review will appear once our team approves it.")
    return redirect(f"{product.get_absolute_url()}#write-review")


def page(request, slug):
    static_page = StaticPage.objects.filter(slug=slug).first()
    if static_page is not None and not static_page.is_published:
        raise Http404
    if static_page is None:
        fallback = STATIC_PAGE_FALLBACKS.get(slug)
        if fallback is None:
            raise Http404
        static_page = StaticPage(slug=slug, **fallback)
    contact_form = None
    if slug == "contact":
        contact_form = ContactForm(request.POST or None)
        if request.method == "POST" and contact_form.is_valid():
            cleaned = contact_form.cleaned_data
            recipient = SiteSettings.load().contact_email or getattr(settings, "EMAIL_HOST_USER", "")
            backend = getattr(settings, "EMAIL_BACKEND", "")
            if not recipient or "console.EmailBackend" in backend:
                from django.contrib import messages
                messages.warning(request, "We could not send this message because email delivery is not configured.")
            else:
                try:
                    sent = send_mail(
                        f"GachGhar contact from {cleaned['name']}",
                        f"Name: {cleaned['name']}\nEmail: {cleaned['email']}\nPhone: {cleaned['phone'] or 'Not provided'}\n\n{cleaned['message']}",
                        settings.DEFAULT_FROM_EMAIL,
                        [recipient],
                        fail_silently=False,
                    )
                except Exception:
                    sent = 0
                if sent:
                    from django.contrib import messages
                    messages.success(request, "Thank you. Your message was sent.")
                    contact_form = ContactForm()
    return render(request, "store/page.html", {"page": static_page, "contact_form": contact_form})


def guides(request):
    return render(request, "store/guides.html", {"guides": Guide.objects.filter(is_published=True)})


def guide_detail(request, slug):
    guide = get_object_or_404(Guide, slug=slug, is_published=True)
    return render(request, "store/guide_detail.html", {"guide": guide})


def blog(request):
    if BlogPost._meta.db_table in connection.introspection.table_names():
        posts = BlogPost.objects.filter(is_published=True)
    else:
        # A code-first release may reach Production before its reviewed schema
        # migration. Keep the public route healthy until BlogPost is available.
        posts = []
    return render(request, "store/blog.html", {"posts": posts})


def blog_detail(request, slug):
    if BlogPost._meta.db_table not in connection.introspection.table_names():
        raise Http404
    post = get_object_or_404(BlogPost, slug=slug, is_published=True)
    return render(request, "store/blog_detail.html", {"post": post})


@require_POST
def newsletter_subscribe(request):
    email = request.POST.get("email", "").strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return _back(request, "Please enter a valid email address.", ok=False)
    NewsletterSubscriber.objects.get_or_create(email=email)
    return _back(request, "Thank you for subscribing.")


def _back(request, message, ok=True):
    from django.contrib import messages
    (messages.success if ok else messages.error)(request, message)
    return redirect(_safe_next(request, "store:home"))


def _safe_next(request, default):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        return target
    return reverse(default)


def robots_txt(request):
    sitemap = request.build_absolute_uri(reverse("sitemap"))
    body = "User-agent: *\nDisallow: /account/\nDisallow: /cart/\nDisallow: /checkout/\nDisallow: /admin/\n" \
           f"Sitemap: {sitemap}\n"
    return HttpResponse(body, content_type="text/plain")


def assistant_page(request):
    return render(request, "store/assistant.html", {"hide_floating_assistant": True})


def _assistant_json_body(request):
    try:
        body = json.loads(request.body or b"{}")
    except (ValueError, AttributeError):
        return None
    return body if isinstance(body, dict) else None


@require_POST
def assistant_api(request):
    body = _assistant_json_body(request)
    message = body.get("message") if body else None
    if not isinstance(message, str) or not message.strip():
        return JsonResponse({"ok": False, "reply": "Please type a question about plants, your cart or orders."},
                            status=400)
    if len(message) > ai_services.MAX_MESSAGE_CHARS:
        return JsonResponse({"ok": False, "reply": f"Please keep your message under {ai_services.MAX_MESSAGE_CHARS} characters."},
                            status=400)
    key = ai_services.client_key(request)
    if not ai_services.within_rate_limit(key):
        return JsonResponse({"ok": False, "reply": "You have sent many messages. Please wait a few minutes."},
                            status=429)
    if not ai_services.within_daily_limit(key):
        return JsonResponse({"ok": False, "reply": "You have reached today's chat limit. Please try again tomorrow, "
                                                   "or continue shopping normally."}, status=429)
    return JsonResponse(ai_services.answer(message, request))


@require_POST
def assistant_confirm(request):
    """Button-press endpoint for consequential actions. The AI model can never call this."""
    body = _assistant_json_body(request) or {}
    token, decision = body.get("token"), body.get("decision")
    if not isinstance(token, str) or decision not in ("confirm", "decline"):
        return JsonResponse({"ok": False, "reply": "Invalid confirmation."}, status=400)
    result = ai_services.confirm(request, token, decision)
    return JsonResponse(result, status=200 if result["ok"] else 400)


@never_cache
def assistant_history(request):
    ai_configured = ai_services.get_provider() is not None
    return JsonResponse({"ok": True, "history": ai_services.get_history(request),
                         "ai_configured": ai_configured,
                         "authenticated": request.user.is_authenticated})


@require_POST
def assistant_clear(request):
    ai_services.clear_history(request)
    return JsonResponse({"ok": True})
