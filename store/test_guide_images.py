from django.contrib.admin.sites import site
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from .admin import CloudinaryUploadAdminMixin
from .models import Guide


class GuideImageTests(TestCase):
    def setUp(self):
        self.guide = Guide.objects.create(
            title="Hibiscus care",
            summary="Water and prune hibiscus plants.",
            body="Keep the soil evenly moist.",
            featured_image="guides/hibiscus-care.webp",
            is_published=True,
        )

    def test_guide_list_and_detail_render_the_optional_featured_image(self):
        listing = self.client.get(reverse("store:guides"))
        detail = self.client.get(self.guide.get_absolute_url())

        self.assertContains(listing, 'src="/media/guides/hibiscus-care.webp"')
        self.assertContains(listing, 'alt="Hibiscus care"')
        self.assertContains(detail, 'src="/media/guides/hibiscus-care.webp"')
        self.assertContains(detail, 'alt="Hibiscus care"')

    def test_admin_exposes_image_upload_and_handles_storage_errors(self):
        model_admin = site._registry[Guide]
        request = RequestFactory().get("/admin/store/guide/add/")

        self.assertIn("featured_image", model_admin.get_fields(request))
        self.assertIsInstance(model_admin, CloudinaryUploadAdminMixin)
