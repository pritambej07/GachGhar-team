import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from store.models import Product, ProductVariant

products = Product.objects.filter(is_active=True).prefetch_related('variants')
print('Total active products:', products.count())
for p in products:
    active_vars = p.variants.filter(is_active=True)
    in_stock = active_vars.filter(stock__gt=0)
    print(f'  {p.name}: active variants={active_vars.count()}, in_stock={in_stock.count()}')