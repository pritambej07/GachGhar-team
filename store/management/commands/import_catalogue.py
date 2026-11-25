from collections import Counter
from decimal import Decimal
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from store.models import Category, Product, ProductVariant


CATEGORIES = (
    {
        "name": "Indoor Plants",
        "slug": "indoor-plants",
        "aliases": ("Live Plants", "Indoor & Foliage Plants"),
    },
    {"name": "Seeds", "slug": "seeds", "aliases": ()},
    {
        "name": "Fertilizers & Soil",
        "slug": "fertilizers-soil",
        "aliases": ("Soil & Fertilizers",),
    },
    {"name": "Pots & Planters", "slug": "pots-planters", "aliases": ()},
    {"name": "Gardening Tools", "slug": "gardening-tools", "aliases": ()},
)


def _product(name, category, price, variant, description_bn, description_en, specifications=(), **matching):
    return {
        "name": name,
        "category": category,
        "price": Decimal(price),
        "variant": variant,
        "description": f"{description_bn}\n\n{description_en}",
        "specifications": tuple(specifications),
        "matching": matching,
    }


CATALOGUE = (
    _product(
        "Money Plant (Golden Pothos)", "Live Plants", "149.00", "Small",
        "সহজে বেড়ে ওঠা সুন্দর indoor climbing plant। ঘর সাজানোর জন্য উপযুক্ত।",
        "An easy-to-grow indoor climbing plant, suitable for decorating the home.",
        ("Botanical name: Epipremnum aureum", "Size: Small", "Light: Indirect sunlight", "Water: Every 5–7 days"),
        aliases=("Golden Money Plant",), allow_single_variant=True,
    ),
    _product(
        "Snake Plant", "Live Plants", "249.00", "Medium",
        "কম যত্নে বেঁচে থাকে এমন সুন্দর ও জনপ্রিয় indoor plant।",
        "A popular indoor plant that thrives with little care.",
        ("Size: Medium", "Light: Low to bright indirect light", "Water: Every 10–15 days"),
        aliases=("Snake Plant / Sansevieria",), allow_single_variant=True,
    ),
    _product(
        "Peace Lily", "Live Plants", "299.00", "Medium",
        "সাদা ফুল ও সবুজ পাতার আকর্ষণীয় indoor flowering plant।",
        "An attractive indoor flowering plant with white flowers and green leaves.",
        ("Size: Medium", "Light: Indirect light", "Water: Weekly, depending on soil moisture"),
    ),
    _product(
        "Jade Plant", "Live Plants", "179.00", "Small",
        "সুন্দর succulent plant, ডেস্ক ও জানালার পাশে রাখার জন্য উপযুক্ত।",
        "A beautiful succulent suitable for desks and windowsills.",
        ("Size: Small", "Light: Bright light", "Water: When soil dries"),
    ),
    _product(
        "Areca Palm", "Live Plants", "399.00", "Medium",
        "ঘরের সৌন্দর্য বাড়ানোর জন্য জনপ্রিয় tropical foliage plant।",
        "A popular tropical foliage plant for adding greenery indoors.",
        ("Size: Medium", "Light: Bright indirect light", "Water: Approximately twice weekly as needed"),
    ),
    _product(
        "Aloe Vera", "Live Plants", "129.00", "Small",
        "কম পানি প্রয়োজন এমন উপকারী succulent plant।",
        "A useful succulent plant that needs little water.",
        ("Size: Small", "Light: Bright sunlight", "Water: Every 10–15 days"),
        aliases=("Aloe Vera Live Plant",), allow_single_variant=True,
    ),
    _product(
        "Rubber Plant", "Live Plants", "349.00", "Medium",
        "বড় চকচকে পাতার premium decorative indoor plant।",
        "A premium decorative indoor plant with large, glossy leaves.",
        ("Botanical name: Ficus elastica", "Size: Medium", "Light: Bright indirect light", "Water: When topsoil dries"),
    ),
    _product(
        "Hibiscus Plant", "Live Plants", "199.00", "Medium",
        "সুন্দর রঙিন ফুল ফোটে এমন outdoor flowering plant।",
        "An outdoor flowering plant with colourful blooms.",
        ("Size: Medium", "Light: 5–6 hours of sunlight", "Water: Regular watering"),
        review_candidates=("Red Hibiscus / Gudhal Live Plant", "Double Pink Hibiscus Live Plant"),
    ),
    _product(
        "Bougainvillea", "Live Plants", "249.00", "Medium",
        "উজ্জ্বল রঙের ফুল ও বাগান সাজানোর জন্য জনপ্রিয় গাছ।",
        "A popular plant with bright colourful flowers for garden decoration.",
        ("Size: Medium", "Light: Full sunlight", "Water: When soil dries"),
        review_candidates=("Pink Bougainvillea Live Plant",),
    ),
    _product(
        "Monstera Deliciosa", "Live Plants", "499.00", "Medium",
        "বড় split-leaf পাতার premium decorative tropical plant।",
        "A premium decorative tropical plant with large split leaves.",
        ("Size: Medium", "Light: Bright indirect light", "Water: Weekly as needed"),
    ),
    _product(
        "Tomato Seeds", "Seeds", "49.00", "30 seeds",
        "বাড়ির ছাদ বা বাগানে টমেটো চাষের জন্য ভালো মানের বীজ।",
        "Seeds for growing tomatoes on a home rooftop or in a garden.",
        ("Pack: 30 seeds", "Type: Vegetable Seeds", "Growing time: Approximately 60–80 days"),
    ),
    _product(
        "Sunflower Seeds", "Seeds", "59.00", "20 seeds",
        "বাগানে সুন্দর হলুদ সূর্যমুখী ফুল ফোটানোর বীজ।",
        "Seeds for growing beautiful yellow sunflowers in the garden.",
        ("Pack: 20 seeds", "Type: Flower Seeds", "Growing time: Approximately 70–100 days"),
    ),
    _product(
        "Coriander Seeds", "Seeds", "39.00", "50 g",
        "বাড়িতে টাটকা ধনেপাতা উৎপাদনের জন্য উপযুক্ত।",
        "Suitable for growing fresh coriander leaves at home.",
        ("Pack: 50 g", "Type: Herb Seeds", "Germination: Approximately 7–14 days"),
    ),
    _product(
        "Spinach Seeds (Palak)", "Seeds", "45.00", "25 g",
        "বাড়ির টব বা ছাদে পালং শাক চাষের জন্য উপযুক্ত।",
        "Suitable for growing spinach in home pots or on a rooftop.",
        ("Pack: 25 g", "Type: Leafy Vegetable Seeds", "Harvest: Approximately 30–45 days"),
    ),
    _product(
        "Organic Vermicompost", "Fertilizers & Soil", "199.00", "5 kg",
        "গাছের মাটির গুণমান ও পুষ্টি উন্নত করতে ব্যবহৃত জৈব সার।",
        "Organic fertilizer used to improve soil quality and plant nutrition.",
        ("Weight: 5 kg", "Type: Organic Fertilizer"),
        family_aliases=("Organic Vermicompost - 1 kg",),
    ),
    _product(
        "Cocopeat Block", "Fertilizers & Soil", "129.00", "1 kg",
        "মাটিতে আর্দ্রতা ধরে রাখতে এবং potting mix তৈরি করতে ব্যবহৃত হয়।",
        "Used to retain moisture in soil and prepare potting mix.",
        ("Weight: 1 kg", "Type: Growing Medium"),
        family_aliases=("Cocopeat Block - 650 g",),
    ),
    _product(
        "Neem Cake Powder", "Fertilizers & Soil", "99.00", "1 kg",
        "মাটির স্বাস্থ্য উন্নত করতে এবং গাছের পরিচর্যায় ব্যবহৃত হয়।",
        "Used to improve soil health and support plant care.",
        ("Weight: 1 kg", "Type: Organic Soil Amendment"),
    ),
    _product(
        "Terracotta Clay Pot", "Pots & Planters", "99.00", "6-inch pot",
        "গাছ লাগানোর জন্য প্রাকৃতিক মাটির টব।",
        "A natural clay pot for planting.",
        ("Size: 6 inch", "Material: Natural Clay"),
    ),
    _product(
        "Ceramic Decorative Pot", "Pots & Planters", "249.00", "5-inch pot",
        "Indoor plants ও ঘর সাজানোর জন্য সুন্দর decorative planter।",
        "A decorative planter for indoor plants and home decor.",
        ("Size: 5 inch", "Material: Ceramic"),
    ),
    _product(
        "Plastic Nursery Pot", "Pots & Planters", "49.00", "6-inch pot",
        "দৈনন্দিন গাছ লাগানো ও nursery ব্যবহারের জন্য হালকা টব।",
        "A lightweight pot for everyday planting and nursery use.",
        ("Size: 6 inch", "Material: Durable Plastic"),
        aliases=("6-Inch Plastic Nursery Pot",), allow_single_variant=True,
    ),
    _product(
        "Hanging Planter", "Pots & Planters", "199.00", "8-inch planter",
        "Balcony, window ও indoor hanging garden সাজানোর জন্য উপযুক্ত।",
        "Suitable for decorating balconies, windows and indoor hanging gardens.",
        ("Size: 8 inch", "Material: Plastic"),
    ),
    _product(
        "Garden Hand Trowel", "Gardening Tools", "149.00", "Standard",
        "মাটি খোঁড়া, চারা লাগানো ও টবের মাটি পরিবর্তনের জন্য ব্যবহারযোগ্য।",
        "For digging soil, planting seedlings and changing potting soil.",
        ("Material: Metal + Wooden Handle", "Use: Digging and planting"),
    ),
    _product(
        "Watering Can", "Gardening Tools", "199.00", "2 litres",
        "গাছের গোড়ায় সহজে ও নিয়ন্ত্রিতভাবে পানি দেওয়ার জন্য।",
        "For controlled watering at plant roots.",
        ("Capacity: 2 litres", "Material: Plastic"),
    ),
    _product(
        "Plant Spray Bottle", "Plant Accessories", "99.00", "500 ml",
        "গাছের পাতায় পানি স্প্রে ও liquid plant care ব্যবহারের জন্য।",
        "For spraying water on leaves and applying liquid plant care.",
        ("Capacity: 500 ml", "Material: Plastic"),
    ),
    _product(
        "Gardening Gloves", "Plant Accessories", "129.00", "Medium",
        "বাগানের কাজ করার সময় হাতকে মাটি ও কাঁটা থেকে সুরক্ষায় সাহায্য করে।",
        "Helps protect hands from soil and thorns during gardening.",
        ("Size: Medium", "Material: Fabric with protective coating"),
    ),
    _product(
        "Pruning Shears", "Plant Accessories", "249.00", "Standard",
        "গাছের শুকনো পাতা, ছোট ডাল ও অতিরিক্ত অংশ কাটার জন্য।",
        "For trimming dry leaves, small branches and excess growth.",
        ("Material: Stainless Steel", "Use: Trimming and pruning"),
    ),
)

# This release plan is intentionally limited to the 15 products the owner
# specified. The broader local catalogue remains available in its own seeder;
# this Production-oriented importer must not add unrelated products/categories.
_REQUESTED_PRODUCT_CATEGORIES = {
    "Money Plant (Golden Pothos)": "Indoor Plants",
    "Snake Plant": "Indoor Plants",
    "Aloe Vera": "Indoor Plants",
    "Coriander Seeds": "Seeds",
    "Tomato Seeds": "Seeds",
    "Sunflower Seeds": "Seeds",
    "Neem Cake Powder": "Fertilizers & Soil",
    "Cocopeat Block": "Fertilizers & Soil",
    "Organic Vermicompost": "Fertilizers & Soil",
    "Plastic Nursery Pot": "Pots & Planters",
    "Terracotta Clay Pot": "Pots & Planters",
    "Ceramic Decorative Pot": "Pots & Planters",
    "Gardening Gloves": "Gardening Tools",
    "Garden Hand Trowel": "Gardening Tools",
    "Pruning Shears": "Gardening Tools",
}

_requested_catalogue = []
for _entry in CATALOGUE:
    _category = _REQUESTED_PRODUCT_CATEGORIES.get(_entry["name"])
    if _category is None:
        continue
    _copy = {**_entry, "category": _category, "matching": dict(_entry["matching"])}
    if _entry["name"] == "Money Plant (Golden Pothos)":
        _copy["name"] = "Money Plant"
        _copy["matching"]["aliases"] = tuple(dict.fromkeys((
            *_copy["matching"].get("aliases", ()),
            "Money Plant (Golden Pothos)",
        )))
    _requested_catalogue.append(_copy)

if len(_requested_catalogue) != len(_REQUESTED_PRODUCT_CATEGORIES):
    raise RuntimeError("The requested product plan does not match its prepared catalogue entries.")

CATALOGUE = tuple(_requested_catalogue)


def _normalize(value):
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _find_named(objects, names):
    keys = {_normalize(name) for name in names}
    return [obj for obj in objects if _normalize(obj.name) in keys]


def _planned_sku(entry):
    return f"GG-PLAN-{slugify(entry['name']).replace('-', '').upper()}"


def _category_plan(categories):
    plans = []
    for definition in CATEGORIES:
        matches = _find_named(categories, (definition["name"], *definition["aliases"]))
        if len(matches) > 1:
            plans.append({"definition": definition, "status": "conflict", "category": None})
        elif matches:
            plans.append({"definition": definition, "status": "reuse", "category": matches[0]})
        else:
            slug_match = next((item for item in categories if item.slug == definition["slug"]), None)
            plans.append({
                "definition": definition,
                "status": "conflict" if slug_match else "create",
                "category": slug_match,
            })
    return plans


def build_import_plan():
    products = list(Product.objects.select_related("category").prefetch_related("variants", "images"))
    categories = list(Category.objects.all())
    category_plans = _category_plan(categories)
    plans = []

    for entry in CATALOGUE:
        candidates = _find_named(products, entry["matching"].get("review_candidates", ()))
        if candidates:
            plans.append({
                "entry": entry, "status": "ambiguous", "product": None, "variant": None,
                "candidates": candidates, "note": "Owner confirmation required before matching.",
            })
            continue

        family_matches = _find_named(products, entry["matching"].get("family_aliases", ()))
        if family_matches:
            plans.append({
                "entry": entry, "status": "variant_pending", "product": family_matches[0],
                "variant": None, "candidates": family_matches,
                "note": "Existing product has a different pack size; new SKU and stock are required.",
            })
            continue

        matches = _find_named(products, (entry["name"], *entry["matching"].get("aliases", ())))
        if len(matches) > 1:
            plans.append({
                "entry": entry, "status": "ambiguous", "product": None, "variant": None,
                "candidates": matches, "note": "Multiple existing products match these names.",
            })
            continue
        if matches:
            product = matches[0]
            variants = list(product.variants.all())
            variant_names = { _normalize(entry["variant"]) }
            variant = next((item for item in variants if _normalize(item.name) in variant_names), None)
            if variant is None and entry["matching"].get("allow_single_variant") and len(variants) == 1:
                variant = variants[0]
            if variant:
                plans.append({
                    "entry": entry, "status": "matched", "product": product, "variant": variant,
                    "candidates": [product], "note": "",
                })
            elif variants:
                plans.append({
                    "entry": entry, "status": "variant_conflict", "product": product, "variant": None,
                    "candidates": [product], "note": "No unique existing variant matches the requested option.",
                })
            else:
                plans.append({
                    "entry": entry, "status": "matched_no_variant", "product": product, "variant": None,
                    "candidates": [product],
                    "note": "Product details can be staged, but price needs a variant with an owner-provided SKU.",
                })
            continue

        slug = slugify(entry["name"])
        slug_match = next((item for item in products if item.slug == slug), None)
        if slug_match:
            plans.append({
                "entry": entry, "status": "slug_conflict", "product": slug_match, "variant": None,
                "candidates": [slug_match], "note": "Generated slug belongs to a different existing product.",
            })
        else:
            sku_match = ProductVariant.objects.filter(sku=_planned_sku(entry)).select_related("product").first()
            if sku_match:
                plans.append({
                    "entry": entry, "status": "sku_conflict", "product": sku_match.product, "variant": sku_match,
                    "candidates": [sku_match.product], "note": "Generated planning SKU is already assigned to another product.",
                })
                continue
            plans.append({
                "entry": entry, "status": "create", "product": None, "variant": None,
                "candidates": [],
                "note": "Will be inactive with the planned price and zero-stock default; add an image and verified stock before publication.",
            })
    return category_plans, plans


class Command(BaseCommand):
    help = "Safely stage the 15 requested products; defaults to a read-only dry run."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write catalogue data. Run only after reviewing the dry run and verifying a current database backup.",
        )
        parser.add_argument(
            "--backup-verified",
            action="store_true",
            help="Acknowledge that a current database backup has been separately verified.",
        )

    def handle(self, *args, **options):
        if options["apply"] and not options["backup_verified"]:
            raise CommandError("--apply requires --backup-verified after a current database backup has been verified.")

        category_plans, plans = build_import_plan()
        self.stdout.write("Catalogue import plan (read-only unless --apply is supplied)")
        self.stdout.write("Categories:")
        for item in category_plans:
            definition = item["definition"]
            detail = item["category"].name if item["category"] else definition["slug"]
            self.stdout.write(f"  {item['status'].upper():7} {definition['name']} ({detail})")

        counts = Counter(item["status"] for item in plans)
        self.stdout.write(f"Requested products: {len(plans)}")
        self.stdout.write(
            "Products: "
            + ", ".join(f"{name}={counts.get(name, 0)}" for name in (
                "matched", "matched_no_variant", "create", "variant_pending", "ambiguous",
                "variant_conflict", "slug_conflict", "sku_conflict",
            ))
        )
        for item in plans:
            entry = item["entry"]
            details = [f"INR {entry['price']}", f"option={entry['variant']}"]
            product = item["product"]
            variant = item["variant"]
            if variant:
                details.extend((
                    f"current_price=INR {variant.price}",
                    f"stock={variant.stock}",
                    f"sku={variant.sku}",
                    f"images={product.images.count()}",
                ))
            if item["candidates"]:
                details.append("existing=" + " | ".join(candidate.name for candidate in item["candidates"]))
            if item["note"]:
                details.append(item["note"])
            self.stdout.write(f"  {item['status'].upper():18} {entry['name']}: " + "; ".join(details))

        self.stdout.write(
            "Images added: 0. Existing images will not be reassigned; image rights were not verified."
        )
        self.stdout.write(
            "Existing products, categories, stock, SKUs, prices, and images are preserved. New products are inactive "
            "with a zero-stock price variant and generated planning SKU; no images or stock are added."
        )

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY RUN ONLY: no database writes were made."))
            return

        missing_categories = [
            item["definition"]["name"] for item in category_plans if item["status"] != "reuse"
        ]
        if missing_categories:
            raise CommandError(
                "Required existing categories are missing or ambiguous; no categories or products were written: "
                + ", ".join(missing_categories)
            )

        self._apply(category_plans, plans)
        self.stdout.write(self.style.SUCCESS(
            "Import applied idempotently; existing categories and matching products were preserved."
        ))

    @transaction.atomic
    def _apply(self, category_plans, plans):
        category_map = {}
        for item in category_plans:
            definition = item["definition"]
            category_map[definition["name"]] = item["category"]

        created = preserved = skipped = 0
        for item in plans:
            entry = item["entry"]
            if item["status"] != "create":
                if item["status"] in {"matched", "matched_no_variant"}:
                    preserved += 1
                else:
                    skipped += 1
                continue

            category = category_map[entry["category"]]
            if item["status"] == "create":
                product = Product.objects.create(
                    name=entry["name"],
                    slug=slugify(entry["name"]),
                    category=category,
                    description=entry["description"],
                    specifications="\n".join(entry["specifications"]),
                    is_active=False,
                )
                ProductVariant.objects.create(
                    product=product,
                    name=entry["variant"],
                    sku=_planned_sku(entry),
                    price=entry["price"],
                )
                created += 1

        self.stdout.write(
            f"Created inactive product stubs: {created}; matching existing products preserved: {preserved}; "
            f"ambiguous or conflicting entries skipped: {skipped}."
        )
