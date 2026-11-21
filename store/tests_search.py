"""Tests for search functionality and live suggestions."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, Product, ProductVariant, StockMovement
from .tests import make_product

User = get_user_model()


class SearchTests(TestCase):
    def setUp(self):
        self.plant, _ = make_product("Snake Plant")
        self.fern, _ = make_product("Boston Fern")
        self.pot, _ = make_product("Ceramic Pot")

    def test_search_by_product_name(self):
        response = self.client.get(reverse("store:search"), {"q": "Snake"})
        self.assertContains(response, "Snake Plant")

    def test_search_by_partial_name(self):
        response = self.client.get(reverse("store:search"), {"q": "Fer"})
        self.assertContains(response, "Boston Fern")

    def test_search_by_category(self):
        response = self.client.get(reverse("store:search"), {"q": "Snake"})
        self.assertContains(response, "Indoor Plants")

    def test_search_case_insensitive(self):
        response = self.client.get(reverse("store:search"), {"q": "snake plant"})
        self.assertContains(response, "Snake Plant")

    def test_search_suggestions_endpoint(self):
        response = self.client.get(reverse("store:search_suggestions"), {"q": "Snak"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["suggestions"]), 1)
        self.assertEqual(data["suggestions"][0]["name"], "Snake Plant")

    def test_search_suggestions_partial_match(self):
        response = self.client.get(reverse("store:search_suggestions"), {"q": "Plant"})
        data = response.json()
        # Should find Snake Plant by partial match in name
        self.assertTrue(any(s["name"] == "Snake Plant" for s in data["suggestions"]))

    def test_search_suggestions_product_link(self):
        response = self.client.get(reverse("store:search_suggestions"), {"q": "snake"})
        data = response.json()
        self.assertIn("url", data["suggestions"][0])
        self.assertIn("snake-plant", data["suggestions"][0]["url"])

    def test_search_suggestions_empty_query(self):
        response = self.client.get(reverse("store:search_suggestions"), {"q": ""})
        data = response.json()
        self.assertEqual(len(data["suggestions"]), 0)

    def test_search_suggestions_short_query(self):
        response = self.client.get(reverse("store:search_suggestions"), {"q": "a"})
        data = response.json()
        self.assertEqual(len(data["suggestions"]), 0)

    def test_no_results_message(self):
        response = self.client.get(reverse("store:search"), {"q": "nonexistentproduct12345"})
        self.assertEqual(response.status_code, 200)

    def test_inactive_products_not_in_suggestions(self):
        make_product("Hidden Plant", active=False)
        response = self.client.get(reverse("store:search_suggestions"), {"q": "Hidden"})
        data = response.json()
        names = [s["name"] for s in data["suggestions"]]
        self.assertNotIn("Hidden Plant", names)