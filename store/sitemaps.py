from django.contrib.sitemaps import Sitemap

from .models import Category, Product


class ProductSitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        return Product.objects.filter(is_active=True)

    def lastmod(self, obj):
        return obj.updated_at


class CategorySitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        return Category.objects.filter(is_active=True)


SITEMAPS = {"products": ProductSitemap, "categories": CategorySitemap}
