from django.test import TestCase
from django.urls import reverse

from .models import BlogPost, Category, Guide, StaticPage
from .tests import make_product


class PublicContentTests(TestCase):
    def test_homepage_falls_back_to_active_categories_and_products(self):
        category = Category.objects.create(name="Indoor Plants", is_active=True)
        product, _ = make_product(name="Fallback Plant")
        product.category = category
        product.save(update_fields=["category"])

        response = self.client.get(reverse("store:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fallback Plant")
        self.assertContains(response, "Indoor Plants")
        self.assertNotContains(response, "Our plant collection is being prepared")

    def test_published_blog_and_detail_work_but_draft_is_hidden(self):
        published = BlogPost.objects.create(
            title="Published GachGhar Article",
            summary="A published article",
            body="Article body.",
            is_published=True,
        )
        draft = BlogPost.objects.create(
            title="Unpublished Draft",
            body="Draft body.",
            is_published=False,
        )

        listing = self.client.get(reverse("store:blog"))
        detail = self.client.get(published.get_absolute_url())

        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Published GachGhar Article")
        self.assertNotContains(listing, "Unpublished Draft")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Article body")
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)

    def test_about_and_contact_static_pages_return_200(self):
        StaticPage.objects.create(
            slug="about",
            title="About GachGhar",
            body="Existing about content.",
            is_published=True,
        )
        StaticPage.objects.create(
            slug="contact",
            title="Contact GachGhar",
            body="Contact body.",
            is_published=True,
        )

        self.assertEqual(self.client.get(reverse("store:page", args=["about"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("store:page", args=["contact"])).status_code, 200)

    def test_contact_post_is_validated_without_claiming_delivery(self):
        StaticPage.objects.create(
            slug="contact",
            title="Contact GachGhar",
            body="Contact body.",
            is_published=True,
        )
        response = self.client.post(
            reverse("store:page", args=["contact"]),
            {"name": "", "email": "invalid", "phone": "", "message": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
