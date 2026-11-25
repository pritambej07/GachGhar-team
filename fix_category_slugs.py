import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from store.models import Category, Product

# Map old slugs to new slugs (matching production/templates)
SLUG_MAP = {
    'indoor-foliage-plants': 'indoor-plants',
    'live-plants': 'indoor-plants',  # This might be merged
    'flowering-plants': 'flowering-plants',  # Keep
    'seeds': 'seeds',  # Keep
    'herbal-medicinal-plants': 'herbal-medicinal-plants',  # Keep
    'soil-fertilizers': 'fertilizers-soil',
    'pots-planters': 'pots-planters',  # Keep
    'gardening-tools': 'gardening-tools',  # Keep
    'plant-accessories': 'plant-accessories',  # Keep
}

def fix_category_slugs():
    for old_slug, new_slug in SLUG_MAP.items():
        if old_slug == new_slug:
            continue
        try:
            cat = Category.objects.get(slug=old_slug)
            # Check if new_slug already exists
            if Category.objects.filter(slug=new_slug).exists():
                print(f"Category with slug '{new_slug}' already exists, merging...")
                # Merge products from old to new
                new_cat = Category.objects.get(slug=new_slug)
                Product.objects.filter(category=cat).update(category=new_cat)
                cat.delete()
                print(f"  Merged '{old_slug}' into '{new_slug}'")
            else:
                cat.slug = new_slug
                cat.save()
                print(f"  Renamed '{old_slug}' -> '{new_slug}'")
        except Category.DoesNotExist:
            print(f"  Category '{old_slug}' not found, skipping")

if __name__ == '__main__':
    fix_category_slugs()
    print("\nDone. Current categories:")
    for c in Category.objects.all().order_by('sort_order', 'name'):
        print(f"  {c.slug} -> {c.name}")