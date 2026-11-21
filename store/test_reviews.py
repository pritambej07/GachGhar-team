"""Review submission, moderation and public visibility. Run: python manage.py test store"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Review
from .tests import make_product

User = get_user_model()


class ReviewTests(TestCase):
    def setUp(self):
        self.product, _ = make_product("Money Plant")
        self.user = User.objects.create_user(username="rita", email="rita@example.com", password="pw-12345-xyz")
        self.url = reverse("store:review_submit", args=[self.product.slug])
        self.valid = {"rating": 5, "title": "Lovely", "body": "Healthy plant, arrived well packed."}

    def test_guest_is_redirected_to_login(self):
        response = self.client.post(self.url, self.valid)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
        self.assertEqual(Review.objects.count(), 0)

    def test_submission_is_pending_and_hidden_publicly(self):
        self.client.force_login(self.user)
        self.client.post(self.url, self.valid)
        review = Review.objects.get()
        self.assertFalse(review.is_approved)
        page = self.client.get(self.product.get_absolute_url())
        self.assertNotContains(page, "Healthy plant, arrived well packed.</p>")
        self.assertContains(page, "waiting for approval")

    def test_approved_review_is_public_and_counted(self):
        self.client.force_login(self.user)
        self.client.post(self.url, self.valid)
        Review.objects.update(is_approved=True)
        page = self.client.get(self.product.get_absolute_url())
        self.assertContains(page, "Healthy plant, arrived well packed.")
        self.assertContains(page, "from 1 review")
        self.assertContains(page, "rating-stars")
        self.assertContains(page, "★")

    def test_pending_review_not_counted_in_rating(self):
        self.client.force_login(self.user)
        self.client.post(self.url, self.valid)
        page = self.client.get(self.product.get_absolute_url())
        self.assertNotContains(page, "from 1 review")

    def test_one_review_per_customer_second_post_updates_and_resets_approval(self):
        self.client.force_login(self.user)
        self.client.post(self.url, self.valid)
        Review.objects.update(is_approved=True)
        self.client.post(self.url, {**self.valid, "rating": 3, "body": "Changed my mind about it."})
        self.assertEqual(Review.objects.count(), 1)
        review = Review.objects.get()
        self.assertEqual(review.rating, 3)
        self.assertFalse(review.is_approved)

    def test_invalid_rating_and_short_text_rejected(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {**self.valid, "rating": 9})
        self.client.post(self.url, {**self.valid, "body": "short"})
        self.assertEqual(Review.objects.count(), 0)

    def test_rejected_review_stays_hidden(self):
        self.client.force_login(self.user)
        self.client.post(self.url, self.valid)
        Review.objects.update(is_approved=True)
        Review.objects.update(is_approved=False)
        page = self.client.get(self.product.get_absolute_url())
        self.assertNotContains(page, "Healthy plant, arrived well packed.</p>")

    def test_inactive_product_cannot_be_reviewed(self):
        hidden, _ = make_product("Hidden", active=False)
        self.client.force_login(self.user)
        response = self.client.post(reverse("store:review_submit", args=[hidden.slug]), self.valid)
        self.assertEqual(response.status_code, 404)
