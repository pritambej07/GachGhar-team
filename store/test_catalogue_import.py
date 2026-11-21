from decimal import Decimal
from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse

from .models import Category, Product, ProductVariant, StockMovement


class CatalogueImportCommandTests(TestCase):
    def setUp(self):
        indoor = Category.objects.create(name="Indoor & Foliage Plants", slug="indoor-foliage-plants")
        pots = Category.objects.create(name="Pots & Planters", slug="pots-planters")
        soil = Category.objects.create(name="Soil & Fertilizers", slug="soil-fertilizers")
        self.money = self._product(
            indoor, "Golden Money Plant", "money-old", "79.00", "GG-OLD-MONEY", "Standard nursery plant"
        )
        self.snake = self._product(
            indoor, "Snake Plant / Sansevieria", "snake-old", "149.00", "GG-OLD-SNAKE", "Standard nursery plant"
        )
        self.aloe = self._product(
            indoor, "Aloe Vera Live Plant", "aloe-old", "79.00", "GG-OLD-ALOE", "Standard nursery plant"
        )
        self.pot = self._product(
            pots, "6-Inch Plastic Nursery Pot", "pot-old", "39.00", "GG-OLD-POT", "6-inch pot", compare_at="99.00"
        )
        self.vermicompost = self._product(
            soil, "Organic Vermicompost - 1 kg", "vermicompost-old", "59.00", "GG-OLD-VERMI", "1 kg pack"
        )
        self.cocopeat = self._product(
            soil, "Cocopeat Block - 650 g", "cocopeat-old", "39.00", "GG-OLD-COCO", "650 g block"
        )
        self.red_hibiscus = self._product(
            Category.objects.create(name="Flowering Plants", slug="flowering-plants"),
            "Red Hibiscus / Gudhal Live Plant", "hibiscus-red", "99.00", "GG-OLD-HIB-RED", "Standard nursery plant",
        )
        self.pink_hibiscus = self._product(
            Category.objects.get(slug="flowering-plants"),
            "Double Pink Hibiscus Live Plant", "hibiscus-pink", "129.00", "GG-OLD-HIB-PINK", "Standard nursery plant",
        )
        self.bougainvillea = self._product(
            Category.objects.get(slug="flowering-plants"),
            "Pink Bougainvillea Live Plant", "bougainvillea-pink", "129.00", "GG-OLD-BOUGAIN", "Standard nursery plant",
        )
        StockMovement.objects.create(
            variant=self.money.variants.get(), change=7, reason=StockMovement.Reason.RESTOCK
        )
        StockMovement.objects.create(
            variant=self.pot.variants.get(), change=98, reason=StockMovement.Reason.RESTOCK
        )

    def _product(self, category, name, slug, price, sku, variant_name, compare_at=None):
        product = Product.objects.create(name=name, slug=slug, category=category, description="Existing description")
        ProductVariant.objects.create(
            product=product,
            name=variant_name,
            sku=sku,
            price=Decimal(price),
            compare_at_price=Decimal(compare_at) if compare_at else None,
        )
        return product

    def test_default_command_is_a_read_only_dry_run(self):
        product_count = Product.objects.count()
        category_count = Category.objects.count()
        money_price = self.money.variants.get().price
        output = StringIO()

        call_command("import_catalogue", stdout=output)

        self.assertIn("DRY RUN ONLY", output.getvalue())
        self.assertIn("Requested products: 26", output.getvalue())
        self.assertIn("matched=4", output.getvalue())
        self.assertIn("variant_pending=2", output.getvalue())
        self.assertIn("ambiguous=2", output.getvalue())
        self.assertEqual(Product.objects.count(), product_count)
        self.assertEqual(Category.objects.count(), category_count)
        self.assertEqual(self.money.variants.get().price, money_price)

    def test_apply_requires_an_explicit_verified_backup_acknowledgement(self):
        product_count = Product.objects.count()
        category_count = Category.objects.count()

        with self.assertRaises(CommandError):
            call_command("import_catalogue", apply=True, stdout=StringIO())

        self.assertEqual(Product.objects.count(), product_count)
        self.assertEqual(Category.objects.count(), category_count)

    def test_import_is_idempotent_and_preserves_inventory_and_existing_comparison_price(self):
        output = StringIO()
        call_command("import_catalogue", apply=True, backup_verified=True, stdout=output)
        first_product_count = Product.objects.count()
        first_category_count = Category.objects.count()
        call_command("import_catalogue", apply=True, backup_verified=True, stdout=StringIO())

        self.money.refresh_from_db()
        self.pot.refresh_from_db()
        self.vermicompost.refresh_from_db()
        self.cocopeat.refresh_from_db()
        self.red_hibiscus.refresh_from_db()
        self.pink_hibiscus.refresh_from_db()
        self.bougainvillea.refresh_from_db()
        self.assertEqual(Product.objects.count(), first_product_count)
        self.assertEqual(Category.objects.count(), first_category_count)
        self.assertEqual(self.money.name, "Money Plant (Golden Pothos)")
        self.assertEqual(self.money.variants.get().price, Decimal("149.00"))
        self.assertEqual(self.money.variants.get().stock, 7)
        self.assertEqual(self.money.variants.get().sku, "GG-OLD-MONEY")
        self.assertEqual(self.pot.variants.get().price, Decimal("49.00"))
        self.assertEqual(self.pot.variants.get().stock, 98)
        self.assertEqual(self.pot.variants.get().compare_at_price, Decimal("99.00"))
        self.assertEqual(self.vermicompost.variants.get().price, Decimal("59.00"))
        self.assertEqual(self.cocopeat.variants.get().price, Decimal("39.00"))
        self.assertTrue(Product.objects.filter(name="Peace Lily", is_active=False, variants__isnull=True).exists())
        self.assertTrue(Product.objects.filter(name="Neem Cake Powder", is_active=False, variants__isnull=True).exists())
        self.assertEqual(self.red_hibiscus.name, "Red Hibiscus / Gudhal Live Plant")
        self.assertEqual(self.pink_hibiscus.name, "Double Pink Hibiscus Live Plant")
        self.assertEqual(self.bougainvillea.name, "Pink Bougainvillea Live Plant")
        detail = self.client.get(reverse("store:product", args=[self.money.slug]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Money Plant (Golden Pothos)")
        self.assertContains(detail, "Indirect sunlight")
        self.assertContains(detail, "₹149")
        category = self.client.get(reverse("store:category", args=["live-plants"]))
        self.assertEqual(category.status_code, 200)
        self.assertContains(category, "Money Plant (Golden Pothos)")
        for slug in (
            "live-plants",
            "seeds",
            "soil-fertilizers",
            "pots-planters",
            "gardening-tools",
            "plant-accessories",
        ):
            self.assertEqual(self.client.get(reverse("store:category", args=[slug])).status_code, 200)
        search = self.client.get(reverse("store:search"), {"q": "Money Plant"})
        self.assertContains(search, "Money Plant (Golden Pothos)")
        self.assertNotContains(search, "Peace Lily")
