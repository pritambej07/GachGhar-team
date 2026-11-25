import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from store.models import Product, Category

cat = Category.objects.filter(slug='indoor-plants').first()
print('Category:', cat)
products = Product.objects.filter(category__in=cat.descendant_ids(), is_active=True)
print('Products in indoor plants:', products.count())
for p in products:
    print('  {} -> {}'.format(p.name, p.slug))