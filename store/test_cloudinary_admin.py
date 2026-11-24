from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .admin import (
    BlogPostAdmin,
    CategoryAdmin,
    CloudinaryUploadAdminMixin,
    ProductAdmin,
    SiteSettingsAdmin,
)
from .models import Product
from .storage import CloudinaryUploadError


class CloudinaryAdminErrorTests(TestCase):
    def test_all_image_admins_use_the_safe_upload_error_handler(self):
        for model_admin in (ProductAdmin, CategoryAdmin, SiteSettingsAdmin, BlogPostAdmin):
            with self.subTest(model_admin=model_admin.__name__):
                self.assertTrue(issubclass(model_admin, CloudinaryUploadAdminMixin))

    def test_image_upload_failure_returns_admin_message_after_rollback(self):
        user = get_user_model().objects.create_superuser(
            username="media-admin", email="media-admin@example.com", password="Safe-admin-pass-123"
        )
        request = RequestFactory().post(reverse("admin:store_product_add"))
        request.user = user
        request.session = self.client.session
        request._messages = FallbackStorage(request)
        request._dont_enforce_csrf_checks = True
        model_admin = ProductAdmin(Product, admin.site)

        with patch.object(ProductAdmin, "_changeform_view", side_effect=CloudinaryUploadError()):
            response = model_admin.changeform_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("admin:store_product_add"))
        self.assertIn("could not be uploaded", " ".join(str(message) for message in get_messages(request)))
