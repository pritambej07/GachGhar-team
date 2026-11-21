from decimal import Decimal
from django.db import transaction
from store.models import Category, HomeSection, Product, ProductVariant
CATEGORIES = [
    ("flowering-plants", "Flowering Plants", 10),
    ("indoor-foliage-plants", "Indoor & Foliage Plants", 20),
    ("herbal-medicinal-plants", "Herbal & Medicinal Plants", 30),
    ("soil-fertilizers", "Soil & Fertilizers", 40),
    ("pots-planters", "Pots & Planters", 50),
]
PRODUCTS = [
    ("GG-FLW-001","red-hibiscus-gudhal","Red Hibiscus / Gudhal Live Plant","flowering-plants","A beautiful flowering plant known for its large, vibrant red blooms. Ideal for sunny balconies, gardens and outdoor spaces.",99,"Standard nursery plant"),
    ("GG-FLW-002","double-pink-hibiscus","Double Pink Hibiscus Live Plant","flowering-plants","A lovely hibiscus variety featuring attractive double pink flowers. Grows well in warm conditions with regular sunlight.",129,"Standard nursery plant"),
    ("GG-FLW-003","desi-red-rose","Desi Red Rose Live Plant","flowering-plants","A classic red flowering rose plant that adds natural beauty and fragrance to home gardens and balconies.",99,"Standard nursery plant"),
    ("GG-FLW-004","pink-button-rose","Pink Button Rose Live Plant","flowering-plants","A compact rose plant with charming pink blooms, suitable for pots, patios and small gardens.",129,"Standard nursery plant"),
    ("GG-FLW-005","french-marigold-genda","French Marigold / Genda Live Plant","flowering-plants","A cheerful flowering plant with bright seasonal blooms. Ideal for garden borders, balcony pots and sunny spaces.",69,"Standard nursery plant"),
    ("GG-FLW-006","chrysanthemum-guldaudi","Chrysanthemum / Guldaudi Live Plant","flowering-plants","A popular flowering plant with colourful blooms, particularly loved for its winter garden display.",99,"Standard nursery plant"),
    ("GG-FLW-007","pink-bougainvillea","Pink Bougainvillea Live Plant","flowering-plants","A sun-loving ornamental plant with beautiful pink bracts. Suitable for outdoor gardens and balconies.",129,"Standard nursery plant"),
    ("GG-FLW-008","mogra-arabian-jasmine","Mogra / Arabian Jasmine Live Plant","flowering-plants","A fragrant jasmine plant known for its delicate white flowers. Perfect for sunny balconies and home gardens.",99,"Standard nursery plant"),
    ("GG-FLW-009","chandni-dwarf-jasmine","Chandni / Dwarf Jasmine Live Plant","flowering-plants","An attractive evergreen shrub featuring elegant white pinwheel-shaped flowers and glossy green leaves.",79,"Standard nursery plant"),
    ("GG-FLW-010","blue-aparajita-butterfly-pea","Blue Aparajita / Butterfly Pea Live Plant","flowering-plants","A beautiful climbing plant producing attractive blue butterfly-shaped flowers. Suitable for trellises and garden walls.",79,"Standard nursery plant"),
    ("GG-FLW-011","madhumalti-rangoon-creeper","Madhumalti / Rangoon Creeper Live Plant","flowering-plants","A vigorous flowering climber with clusters of fragrant flowers that change colour as they mature.",119,"Standard nursery plant"),
    ("GG-FLW-012","sadabahar-periwinkle","Sadabahar / Periwinkle Live Plant","flowering-plants","An easy-growing flowering plant that produces colourful blooms and performs well in warm weather.",59,"Standard nursery plant"),
    ("GG-FLW-013","portulaca-moss-rose","Portulaca / Moss Rose Live Plant","flowering-plants","A colourful, sun-loving flowering plant with bright blooms. Excellent for sunny balconies and low-maintenance gardens.",59,"Standard nursery plant"),
    ("GG-FLW-014","zinnia-mixed-colour","Zinnia Mixed Colour Live Plant","flowering-plants","A cheerful seasonal flowering plant available in vibrant colours, ideal for sunny gardens and containers.",69,"Standard nursery plant"),
    ("GG-FLW-015","rain-lily","Rain Lily Live Plant","flowering-plants","A charming bulbous flowering plant known for its attractive blooms, often appearing after rainfall.",79,"Standard nursery plant"),
    ("GG-FLW-016","dianthus-mixed-colour","Dianthus Mixed Colour Live Plant","flowering-plants","A compact seasonal flowering plant with attractive colourful flowers, ideal for winter gardens and pots.",89,"Standard nursery plant"),
    ("GG-FLW-017","dahlia-flowering-plant","Dahlia Flowering Live Plant","flowering-plants","A popular seasonal flowering plant producing beautiful ornamental blooms in a variety of colours.",129,"Standard nursery plant"),
    ("GG-FLW-018","crossandra-firecracker-flower","Crossandra / Firecracker Flower Live Plant","flowering-plants","A tropical flowering plant with attractive orange blooms and lush green foliage, suitable for warm gardens.",79,"Standard nursery plant"),
    ("GG-IND-019","golden-money-plant","Golden Money Plant","indoor-foliage-plants","A popular foliage plant featuring attractive golden-green leaves. Suitable for indoor spaces with bright indirect light.",79,"Standard nursery plant"),
    ("GG-IND-020","snake-plant-sansevieria","Snake Plant / Sansevieria","indoor-foliage-plants","A hardy ornamental foliage plant with upright patterned leaves, ideal for homes and offices.",149,"Standard nursery plant"),
    ("GG-IND-021","aloe-vera-live-plant","Aloe Vera Live Plant","indoor-foliage-plants","A popular succulent plant with fleshy green leaves, suitable for sunny windows and well-drained soil.",79,"Standard nursery plant"),
    ("GG-HRB-022","rama-tulsi-live-plant","Rama Tulsi Live Plant","herbal-medicinal-plants","A traditional aromatic herb with green leaves, suitable for home gardens and sunny balconies.",49,"Standard nursery plant"),
    ("GG-SOIL-023","organic-potting-mix-1kg","Organic Potting Mix - 1 kg","soil-fertilizers","A ready-to-use growing medium designed to support healthy plant growth in pots and containers.",49,"1 kg pack"),
    ("GG-SOIL-024","organic-vermicompost-1kg","Organic Vermicompost - 1 kg","soil-fertilizers","Organic compost that helps improve soil structure and adds nutrients to garden soil.",59,"1 kg pack"),
    ("GG-SOIL-025","cocopeat-block-650g","Cocopeat Block - 650 g","soil-fertilizers","A lightweight growing medium made from coconut husk, useful for improving moisture retention and soil aeration.",39,"650 g block"),
    ("GG-POT-026","six-inch-plastic-nursery-pot","6-Inch Plastic Nursery Pot","pots-planters","A lightweight nursery pot with drainage holes, suitable for growing and maintaining ornamental plants.",39,"6-inch pot"),
]
@transaction.atomic
def setup_catalogue():
    category_map = {}
    cc = pc = vc = 0
    for slug, name, order in CATEGORIES:
        obj, created = Category.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "is_active": True, "sort_order": order},
        )
        category_map[slug] = obj
        cc += int(created)
    for sku, slug, name, cat, desc, price, variant_name in PRODUCTS:
        product, created = Product.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "category": category_map[cat],
                "description": desc,
                "is_active": False,
                "is_featured": False,
            },
        )
        pc += int(created)
        if product.category_id != category_map[cat].pk:
            raise RuntimeError("Product/category mismatch: " + slug)
        variant, created = ProductVariant.objects.get_or_create(
            sku=sku,
            defaults={
                "product": product,
                "name": variant_name,
                "price": Decimal(str(price)),
                "is_active": False,
                "stock": 0,
            },
        )
        if variant.product_id != product.pk:
            raise RuntimeError("SKU already belongs to another product: " + sku)
        vc += int(created)
    HomeSection.objects.get_or_create(
        kind=HomeSection.Kind.CATEGORIES,
        title="Shop by Category",
        defaults={"enabled": True, "sort_order": 10},
    )
    print("\nGACHGHAR CATALOGUE SETUP SUCCESS")
    print("New categories:", cc, "| Total:", Category.objects.count())
    print("New products:", pc, "| Total:", Product.objects.count())
    print("New variants:", vc, "| Total:", ProductVariant.objects.count())
    print("All 26 products are initially inactive.")
    print("No fake images or stock quantities have been added.")
setup_catalogue()
