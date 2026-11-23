from django.core.management import call_command
from django.test import TestCase

from .models import Guide, HomeSection, SiteSettings, StaticPage


class SeedGachGharContentTests(TestCase):
    def setUp(self):
        self.about = StaticPage.objects.create(
            slug="about",
            title="About GachGhar",
            body="Existing owner copy.",
            is_published=True,
        )
        self.contact = StaticPage.objects.create(
            slug="contact",
            title="Contact GachGhar",
            body="Existing contact copy.",
            is_published=True,
        )

    def test_preview_and_apply_are_safe_and_repeatable(self):
        call_command("seed_gachghar_content", stdout=None)
        self.assertEqual(StaticPage.objects.count(), 2)
        self.assertEqual(Guide.objects.count(), 0)

        call_command("seed_gachghar_content", "--apply", stdout=None)
        call_command("seed_gachghar_content", "--apply", stdout=None)

        self.about.refresh_from_db()
        self.contact.refresh_from_db()
        self.assertIn("Existing owner copy.", self.about.body)
        self.assertIn("accessible", self.about.body)
        self.assertEqual(self.about.body.count("Gardening can begin with one plant."), 1)
        self.assertEqual(self.contact.body, "Existing contact copy.")
        self.assertEqual(StaticPage.objects.filter(is_published=True).count(), 6)
        self.assertEqual(Guide.objects.filter(is_published=True).count(), 11)
        self.assertTrue(HomeSection.objects.filter(kind=HomeSection.Kind.GUIDES, enabled=True).exists())
        for page in StaticPage.objects.filter(is_published=True):
            with self.subTest(page=page.slug):
                self.assertEqual(self.client.get(page.get_absolute_url()).status_code, 200)
        for guide in Guide.objects.filter(is_published=True):
            with self.subTest(guide=guide.slug):
                self.assertEqual(self.client.get(guide.get_absolute_url()).status_code, 200)

    def test_contact_page_displays_only_configured_owner_details(self):
        SiteSettings.objects.create(
            legal_entity_name="Owner-provided nursery name",
            grievance_officer_name="Owner-provided officer",
            grievance_email="grievance@example.test",
            grievance_phone="1234567890",
            grievance_hours="Monday to Friday, 10:00–17:00",
        )

        response = self.client.get("/pages/contact/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owner-provided nursery name")
        self.assertContains(response, "Owner-provided officer")
        self.assertContains(response, "mailto:grievance@example.test")
        self.assertContains(response, "Monday to Friday")

    def test_unpublished_conflicting_drafts_are_not_overwritten_or_published(self):
        policy = StaticPage.objects.create(
            slug="privacy",
            title="Private draft",
            body="Owner draft text.",
            is_published=False,
        )
        guide = Guide.objects.create(
            slug="hibiscus-plant-care",
            title="Private guide draft",
            summary="Owner summary.",
            body="Owner guide text.",
            is_published=False,
        )

        call_command("seed_gachghar_content", "--apply", stdout=None)

        policy.refresh_from_db()
        guide.refresh_from_db()
        self.assertFalse(policy.is_published)
        self.assertEqual(policy.body, "Owner draft text.")
        self.assertFalse(guide.is_published)
        self.assertEqual(guide.body, "Owner guide text.")
