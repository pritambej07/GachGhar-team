from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from .models import Category, Product, ProductVariant, StockMovement


class SeedGachGharCatalogueTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Owner category name",
            slug="flowering-plants",
            is_active=False,
        )
        self.product = Product.objects.create(
            name="Owner product name",
            slug="red-hibiscus-gudhal",
            category=self.category,
            description="Owner description",
            is_active=False,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            name="Owner variant name",
            sku="GG-FLW-001",
            price=Decimal("123.00"),
            is_active=False,
        )
        StockMovement.objects.create(
            variant=self.variant,
            change=7,
            reason=StockMovement.Reason.RESTOCK,
            note="Existing ledger balance",
        )

    def test_seed_activates_catalogue_without_overwriting_owner_data_or_stock(self):
        call_command("seed_gachghar_catalogue", "--apply", stdout=None)
        call_command("seed_gachghar_catalogue", "--apply", stdout=None)

        self.category.refresh_from_db()
        self.product.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertTrue(self.category.is_active)
        self.assertEqual(self.category.name, "Owner category name")
        self.assertTrue(self.product.is_active)
        self.assertEqual(self.product.name, "Owner product name")
        self.assertEqual(self.product.description, "Owner description")
        self.assertEqual(self.product.category_id, self.category.pk)
        self.assertTrue(self.variant.is_active)
        self.assertEqual(self.variant.name, "Owner variant name")
        self.assertEqual(self.variant.price, Decimal("123.00"))
        self.assertEqual(self.variant.stock, 7)
        self.assertEqual(StockMovement.objects.filter(variant=self.variant).count(), 1)
        self.assertEqual(Product.objects.count(), 26)
        self.assertEqual(ProductVariant.objects.count(), 26)
        self.assertEqual(Category.objects.count(), 5)
        self.assertEqual(self.product.images.count(), 0)

    def test_seed_defaults_to_a_non_persistent_preview(self):
        call_command("seed_gachghar_catalogue", stdout=None)

        self.category.refresh_from_db()
        self.product.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertFalse(self.category.is_active)
        self.assertFalse(self.product.is_active)
        self.assertFalse(self.variant.is_active)
        self.assertEqual(Category.objects.count(), 1)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(ProductVariant.objects.count(), 1)
        self.assertEqual(self.variant.stock, 7)

    def test_seed_skips_category_conflicts_and_continues_safely(self):
        other_category = Category.objects.create(name="Existing category", slug="existing-category")
        conflicting_product = Product.objects.create(
            name="Existing money plant",
            slug="golden-money-plant",
            category=other_category,
            is_active=False,
        )
        conflicting_variant = ProductVariant.objects.create(
            product=conflicting_product,
            name="Existing size",
            sku="GG-IND-019",
            price=Decimal("88.00"),
            is_active=False,
        )

        call_command("seed_gachghar_catalogue", "--apply", stdout=None)

        conflicting_product.refresh_from_db()
        conflicting_variant.refresh_from_db()
        self.assertEqual(conflicting_product.category_id, other_category.pk)
        self.assertFalse(conflicting_product.is_active)
        self.assertFalse(conflicting_variant.is_active)
        self.assertEqual(conflicting_variant.price, Decimal("88.00"))
        self.assertEqual(Product.objects.filter(slug="golden-money-plant").count(), 1)
        self.assertEqual(ProductVariant.objects.filter(sku="GG-IND-019").count(), 1)
        self.assertTrue(Product.objects.get(slug="double-pink-hibiscus").is_active)
