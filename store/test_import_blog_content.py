from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse

from .models import BlogPost


class ImportBlogContentTests(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.fixture_path = Path(self.temp_dir.name) / "blog.json"
        self.records = [
            {
                "slug": "watering-indoor-plants",
                "title": "Watering Indoor Plants",
                "summary": "Check soil and drainage before watering.",
                "body": "Water the soil evenly and let excess drain.",
                "is_published": True,
            },
            {
                "slug": "draft-garden-note",
                "title": "Draft Garden Note",
                "summary": "A draft post.",
                "body": "This post is not public yet.",
                "is_published": False,
            },
        ]
        self.write_fixture(self.records)

    def write_fixture(self, records):
        self.fixture_path.write_text(json.dumps(records), encoding="utf-8")

    def run_import(self, *args):
        output = StringIO()
        call_command("import_blog_content", "--file", str(self.fixture_path), *args, stdout=output)
        return output.getvalue()

    def test_preview_apply_is_idempotent_and_publishes_only_marked_posts(self):
        output = self.run_import()
        self.assertIn("would create 2", output)
        self.assertEqual(BlogPost.objects.count(), 0)

        output = self.run_import("--apply")
        self.assertIn("Created: 2", output)
        self.assertEqual(BlogPost.objects.count(), 2)
        post = BlogPost.objects.get(slug="watering-indoor-plants")
        self.assertIsNotNone(post.published_at)
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(reverse("store:blog_detail", args=["draft-garden-note"])).status_code, 404)

        output = self.run_import("--apply")
        self.assertIn("unchanged: 2", output)
        self.assertEqual(BlogPost.objects.count(), 2)

    def test_existing_owner_post_is_never_overwritten(self):
        existing = BlogPost.objects.create(
            slug="draft-garden-note", title="Owner Draft", summary="Owner summary.",
            body="Keep this owner copy.", is_published=False,
        )

        output = self.run_import("--apply")

        existing.refresh_from_db()
        self.assertIn("Conflict left unchanged: draft-garden-note", output)
        self.assertEqual(existing.title, "Owner Draft")
        self.assertEqual(existing.body, "Keep this owner copy.")
        self.assertFalse(existing.is_published)
        self.assertTrue(BlogPost.objects.filter(slug="watering-indoor-plants").exists())

    def test_duplicate_fixture_slugs_are_rejected_before_writing(self):
        self.write_fixture([self.records[0], self.records[0]])

        with self.assertRaises(CommandError):
            self.run_import("--apply")

        self.assertEqual(BlogPost.objects.count(), 0)
