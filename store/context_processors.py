from django.conf import settings
from django.db.models import Prefetch

from .models import Category, SiteSettings, StaticPage
from .services import cart_item_count


def site_context(request):
    top_categories = (Category.objects.filter(is_active=True, parent__isnull=True)
                      .prefetch_related(Prefetch("children", queryset=Category.objects.filter(is_active=True))))
    return {
        "site": SiteSettings.load(),
        "nav_categories": top_categories,
        "footer_pages": StaticPage.objects.filter(is_published=True).exclude(slug__in=("about", "contact")),
        "cart_count": cart_item_count(request),
        "max_quantity": settings.CART_MAX_QUANTITY,
    }
