import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase

from .storage import CloudinaryMediaStorage, CloudinaryUploadError


class CloudinaryMediaStorageTests(SimpleTestCase):
    def test_save_uploads_to_cloudinary_without_overwriting_and_returns_asset_name(self):
        upload = Mock(return_value={"public_id": "products/aloe-unique", "format": "webp"})
        uploader = SimpleNamespace(upload=upload)
        cloudinary = ModuleType("cloudinary")
        cloudinary.uploader = uploader

        with patch.dict(sys.modules, {"cloudinary": cloudinary}):
            saved_name = CloudinaryMediaStorage().save(
                "products/aloe.webp", ContentFile(b"image bytes", name="aloe.webp")
            )

        self.assertEqual(saved_name, "products/aloe-unique.webp")
        self.assertEqual(upload.call_args.kwargs["resource_type"], "image")
        self.assertFalse(upload.call_args.kwargs["overwrite"])
        self.assertFalse(upload.call_args.kwargs["unique_filename"])

    def test_upload_errors_are_wrapped_without_provider_details(self):
        upload = Mock(side_effect=RuntimeError("private provider response"))
        uploader = SimpleNamespace(upload=upload)
        cloudinary = ModuleType("cloudinary")
        cloudinary.uploader = uploader

        with patch.dict(sys.modules, {"cloudinary": cloudinary}):
            with self.assertRaises(CloudinaryUploadError) as error:
                CloudinaryMediaStorage().save(
                    "products/aloe.webp", ContentFile(b"image bytes", name="aloe.webp")
                )

        self.assertNotIn("private provider response", str(error.exception))

    def test_url_uses_secure_cloudinary_image_url(self):
        cloudinary_url = Mock(return_value=("https://res.cloudinary.com/example/image/upload/products/aloe.jpg", {}))
        cloudinary = ModuleType("cloudinary")
        utils = ModuleType("cloudinary.utils")
        utils.cloudinary_url = cloudinary_url

        with patch.dict(sys.modules, {"cloudinary": cloudinary, "cloudinary.utils": utils}):
            url = CloudinaryMediaStorage().url("products/aloe.jpg")

        self.assertTrue(url.startswith("https://"))
        self.assertEqual(cloudinary_url.call_args.args[0], "products/aloe")
        self.assertEqual(cloudinary_url.call_args.kwargs["resource_type"], "image")
        self.assertTrue(cloudinary_url.call_args.kwargs["secure"])
