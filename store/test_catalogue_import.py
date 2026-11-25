from decimal import Decimal
from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase

from .models import Category, Product, ProductVariant, StockMovement


class CatalogueImportCommandTests(TestCase):
    def setUp(self):
        indoor = Category.objects.create(name="Indoor & Foliage Plants", slug="indoor-foliage-plants")
        seeds = Category.objects.create(name="Seeds", slug="seeds")
        soil = Category.objects.create(name="Soil & Fertilizers", slug="soil-fertilizers")
        pots = Category.objects.create(name="Pots & Planters", slug="pots-planters")
        tools = Category.objects.create(name="Gardening Tools", slug="gardening-tools")

        self.money = self._product(indoor, "Golden Money Plant", "money-old", "79.00", "GG-OLD-MONEY", "Small")
        self.snake = self._product(
            indoor, "Snake Plant / Sansevieria", "snake-old", "149.00", "GG-OLD-SNAKE", "Medium"
        )
        self.aloe = self._product(indoor, "Aloe Vera Live Plant", "aloe-old", "79.00", "GG-OLD-ALOE", "Small")
        self.tomato = self._product(seeds, "Tomato Seeds", "tomato-old", "35.00", "GG-OLD-TOMATO", "30 seeds")
        self.pot = self._product(
            pots, "6-Inch Plastic Nursery Pot", "pot-old", "39.00", "GG-OLD-POT", "6-inch pot", compare_at="99.00"
        )
        self.vermicompost = self._product(
            soil, "Organic Vermicompost - 1 kg", "vermicompost-old", "59.00", "GG-OLD-VERMI", "1 kg"
        )
        StockMovement.objects.create(
            variant=self.money.variants.get(), change=7, reason=StockMovement.Reason.RESTOCK
        )
        StockMovement.objects.create(
            variant=self.pot.variants.get(), change=98, reason=StockMovement.Reason.RESTOCK
        )
        self.assertEqual(Category.objects.count(), 5)

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

    def test_default_command_previews_only_the_15_requested_products(self):
        product_count = Product.objects.count()
        category_count = Category.objects.count()
        output = StringIO()

        call_command("import_catalogue", stdout=output)

        self.assertIn("Requested products: 15", output.getvalue())
        self.assertIn("matched=5", output.getvalue())
        self.assertIn("variant_pending=1", output.getvalue())
        self.assertIn("create=9", output.getvalue())
        self.assertIn("DRY RUN ONLY", output.getvalue())
        self.assertEqual(Product.objects.count(), product_count)
        self.assertEqual(Category.objects.count(), category_count)

    def test_apply_requires_backup_acknowledgement(self):
        with self.assertRaises(CommandError):
            call_command("import_catalogue", apply=True, stdout=StringIO())
        self.assertEqual(Product.objects.count(), 6)
        self.assertEqual(Category.objects.count(), 5)

    def test_apply_creates_only_inactive_stubs_and_preserves_all_existing_records(self):
        output = StringIO()
        call_command("import_catalogue", apply=True, backup_verified=True, stdout=output)

        self.assertEqual(Category.objects.count(), 5)
        self.assertEqual(Product.objects.count(), 15)
        self.assertEqual(Product.objects.filter(is_active=False, variants__isnull=False).count(), 9)
        self.assertIn("matching existing products preserved: 5", output.getvalue())

        for product, original_name, original_category, original_price, original_sku, original_stock in (
            (self.money, "Golden Money Plant", "indoor-foliage-plants", Decimal("79.00"), "GG-OLD-MONEY", 7),
            (self.snake, "Snake Plant / Sansevieria", "indoor-foliage-plants", Decimal("149.00"), "GG-OLD-SNAKE", 0),
            (self.aloe, "Aloe Vera Live Plant", "indoor-foliage-plants", Decimal("79.00"), "GG-OLD-ALOE", 0),
            (self.tomato, "Tomato Seeds", "seeds", Decimal("35.00"), "GG-OLD-TOMATO", 0),
            (self.pot, "6-Inch Plastic Nursery Pot", "pots-planters", Decimal("39.00"), "GG-OLD-POT", 98),
            (self.vermicompost, "Organic Vermicompost - 1 kg", "soil-fertilizers", Decimal("59.00"), "GG-OLD-VERMI", 0),
        ):
            product.refresh_from_db()
            variant = product.variants.get()
            self.assertEqual(product.name, original_name)
            self.assertEqual(product.category.slug, original_category)
            self.assertEqual(variant.price, original_price)
            self.assertEqual(variant.sku, original_sku)
            self.assertEqual(variant.stock, original_stock)

        expected_prices = {
            "Coriander Seeds": Decimal("39.00"),
            "Sunflower Seeds": Decimal("59.00"),
            "Neem Cake Powder": Decimal("99.00"),
            "Cocopeat Block": Decimal("129.00"),
            "Terracotta Clay Pot": Decimal("99.00"),
            "Ceramic Decorative Pot": Decimal("249.00"),
            "Gardening Gloves": Decimal("129.00"),
            "Garden Hand Trowel": Decimal("149.00"),
            "Pruning Shears": Decimal("249.00"),
        }
        expected_categories = {
            "Coriander Seeds": "seeds",
            "Sunflower Seeds": "seeds",
            "Neem Cake Powder": "soil-fertilizers",
            "Cocopeat Block": "soil-fertilizers",
            "Terracotta Clay Pot": "pots-planters",
            "Ceramic Decorative Pot": "pots-planters",
            "Gardening Gloves": "gardening-tools",
            "Garden Hand Trowel": "gardening-tools",
            "Pruning Shears": "gardening-tools",
        }
        for name, expected_price in expected_prices.items():
            stub = Product.objects.get(name=name)
            self.assertFalse(stub.is_active)
            variant = stub.variants.get()
            self.assertEqual(variant.price, expected_price)
            self.assertEqual(variant.stock, 0)
            self.assertTrue(variant.sku.startswith("GG-PLAN-"))
            self.assertEqual(stub.category.slug, expected_categories[name])
            self.assertFalse(stub.images.exists())

        count_after_first_apply = Product.objects.count()
        call_command("import_catalogue", apply=True, backup_verified=True, stdout=StringIO())
        self.assertEqual(Product.objects.count(), count_after_first_apply)
        self.assertEqual(Category.objects.count(), 5)

    def test_missing_existing_category_blocks_apply_without_creating_or_writing(self):
        Category.objects.get(slug="gardening-tools").delete()

        with self.assertRaisesMessage(CommandError, "Required existing categories are missing or ambiguous"):
            call_command("import_catalogue", apply=True, backup_verified=True, stdout=StringIO())

        self.assertEqual(Product.objects.count(), 6)
        self.assertEqual(Category.objects.count(), 4)
