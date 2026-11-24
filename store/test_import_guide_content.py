from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse
from .models import Guide


class ImportGuideContentTests(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.fixture_path = Path(self.temp_dir.name) / "guides.json"
        self.records = [
            {
                "slug": "indoor-care",
                "title": "Indoor Plant Care",
                "summary": "Care for indoor plants.",
                "body": "Check the light and soil before watering.",
                "is_published": True,
                "sort_order": 5,
            },
            {
                "slug": "draft-guide",
                "title": "Draft Guide",
                "summary": "Not yet published.",
                "body": "Keep this guide unpublished.",
                "is_published": False,
                "sort_order": 10,
            },
        ]
        self.write_fixture(self.records)

    def write_fixture(self, records):
        self.fixture_path.write_text(json.dumps(records), encoding="utf-8")

    def run_import(self, *args):
        output = StringIO()
        call_command("import_guide_content", "--file", str(self.fixture_path), *args, stdout=output)
        return output.getvalue()

    def test_preview_then_apply_is_idempotent_and_preserves_publication_status(self):
        output = self.run_import()
        self.assertIn("would create 2", output)
        self.assertEqual(Guide.objects.count(), 0)

        output = self.run_import("--apply")
        self.assertIn("Created: 2", output)
        self.assertIn("unchanged: 0", output)
        self.assertEqual(Guide.objects.count(), 2)
        self.assertEqual(
            self.client.get(reverse("store:guide", args=["indoor-care"])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("store:guide", args=["draft-guide"])).status_code,
            404,
        )

        output = self.run_import("--apply")
        self.assertIn("Created: 0", output)
        self.assertIn("unchanged: 2", output)
        self.assertEqual(Guide.objects.count(), 2)

    def test_conflicting_existing_record_is_never_overwritten_or_published(self):
        draft = Guide.objects.create(
            slug="draft-guide",
            title="Owner Draft",
            summary="Owner summary.",
            body="Owner content.",
            is_published=False,
        )

        output = self.run_import("--apply")

        draft.refresh_from_db()
        self.assertIn("Conflict left unchanged: draft-guide", output)
        self.assertEqual(draft.title, "Owner Draft")
        self.assertEqual(draft.body, "Owner content.")
        self.assertFalse(draft.is_published)
        self.assertTrue(Guide.objects.filter(slug="indoor-care").exists())

    def test_duplicate_fixture_slugs_are_rejected_before_writing(self):
        self.write_fixture([self.records[0], self.records[0]])

        with self.assertRaises(CommandError):
            self.run_import("--apply")

        self.assertEqual(Guide.objects.count(), 0)
