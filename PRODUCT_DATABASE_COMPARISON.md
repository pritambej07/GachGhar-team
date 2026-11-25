# GachGhar Production Database Comparison Audit

**Audit date:** 2026-11-24
**Mode:** Read-only audit only

## Production connection status

- Neon `DATABASE_URL` is not configured in the current local environment.
- A production read-only connection was therefore **not established**.
- No production data, counts, or product differences could be verified.
- This report makes no production assumptions.

## Local database summary

- Total products: 44
- Active products: 27
- Inactive products: 17
- Categories: 9
- Variants: 27
- Product image records: 1
- Products without image records: 43
- Active variants with zero stock: 25
- Duplicate product names: 0
- Duplicate slugs: 0
- Duplicate SKUs: 0

## Production comparison

**Production product count: UNKNOWN — read-only Neon connection unavailable**

## Local product inventory

| Name | Slug | Category | Active | Variants/SKU/Price/Stock/Active | Image paths | Local issues |
|---|---|---|---|---|---|---|
| Aloe Vera | aloe-vera-live-plant | Live Plants | True | Small\|GG-IND-021\|129.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Areca Palm | areca-palm | Live Plants | False | NONE | NONE | missing_image, missing_variant |
| Blue Aparajita / Butterfly Pea Live Plant | blue-aparajita-butterfly-pea | Flowering Plants | True | Standard nursery plant\|GG-FLW-010\|79.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Ceramic Decorative Pot | ceramic-decorative-pot | Pots & Planters | False | NONE | NONE | missing_image, missing_variant |
| Chandni / Dwarf Jasmine Live Plant | chandni-dwarf-jasmine | Flowering Plants | True | Standard nursery plant\|GG-FLW-009\|79.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Chrysanthemum / Guldaudi Live Plant | chrysanthemum-guldaudi | Flowering Plants | True | Standard nursery plant\|GG-FLW-006\|99.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Cocopeat Block - 650 g | cocopeat-block-650g | Soil & Fertilizers | True | 650 g block\|GG-SOIL-025\|39.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Coriander Seeds | coriander-seeds | Seeds | False | NONE | NONE | missing_image, missing_variant |
| Crossandra / Firecracker Flower Live Plant | crossandra-firecracker-flower | Flowering Plants | True | Standard nursery plant\|GG-FLW-018\|79.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Dahlia Flowering Live Plant | dahlia-flowering-plant | Flowering Plants | True | Standard nursery plant\|GG-FLW-017\|129.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Desi Red Rose Live Plant | desi-red-rose | Flowering Plants | True | Standard nursery plant\|GG-FLW-003\|99.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Dianthus Mixed Colour Live Plant | dianthus-mixed-colour | Flowering Plants | True | Standard nursery plant\|GG-FLW-016\|89.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Double Pink Hibiscus Live Plant | double-pink-hibiscus | Flowering Plants | True | Standard nursery plant\|GG-FLW-002\|129.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| French Marigold / Genda Live Plant | french-marigold-genda | Flowering Plants | True | Standard nursery plant\|GG-FLW-005\|69.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Garden Hand Trowel | garden-hand-trowel | Gardening Tools | False | NONE | NONE | missing_image, missing_variant |
| Gardening Gloves | gardening-gloves | Plant Accessories | False | NONE | NONE | missing_image, missing_variant |
| Hanging Planter | hanging-planter | Pots & Planters | False | NONE | NONE | missing_image, missing_variant |
| Jade Plant | jade-plant | Live Plants | False | NONE | NONE | missing_image, missing_variant |
| Madhumalti / Rangoon Creeper Live Plant | madhumalti-rangoon-creeper | Flowering Plants | True | Standard nursery plant\|GG-FLW-011\|119.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Mogra / Arabian Jasmine Live Plant | mogra-arabian-jasmine | Flowering Plants | True | Standard nursery plant\|GG-FLW-008\|99.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Money Plant (Golden Pothos) | golden-money-plant | Live Plants | True | Small\|GG-IND-019\|149.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Monstera Deliciosa | monstera-deliciosa | Live Plants | False | NONE | NONE | missing_image, missing_variant |
| Neem Cake Powder | neem-cake-powder | Soil & Fertilizers | False | NONE | NONE | missing_image, missing_variant |
| Organic Potting Mix - 1 kg | organic-potting-mix-1kg | Soil & Fertilizers | True | 1 kg pack\|GG-SOIL-023\|49.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Organic Vermicompost - 1 kg | organic-vermicompost-1kg | Soil & Fertilizers | True | 1 kg pack\|GG-SOIL-024\|59.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Peace Lily | peace-lily | Live Plants | False | NONE | NONE | missing_image, missing_variant |
| Pink Bougainvillea Live Plant | pink-bougainvillea | Flowering Plants | True | Standard nursery plant\|GG-FLW-007\|129.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Pink Button Rose Live Plant | pink-button-rose | Flowering Plants | True | Standard nursery plant\|GG-FLW-004\|129.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Plant Spray Bottle | plant-spray-bottle | Plant Accessories | True | Standard\|GG-AC-001\|250.00\|stock=100\|active=True | NONE | missing_image |
| Plastic Nursery Pot | six-inch-plastic-nursery-pot | Pots & Planters | True | 6-inch pot\|GG-POT-026\|49.00\|stock=82\|active=True | products/images.jpg | none |
| Portulaca / Moss Rose Live Plant | portulaca-moss-rose | Flowering Plants | True | Standard nursery plant\|GG-FLW-013\|59.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Pruning Shears | pruning-shears | Plant Accessories | False | NONE | NONE | missing_image, missing_variant |
| Rain Lily Live Plant | rain-lily | Flowering Plants | True | Standard nursery plant\|GG-FLW-015\|79.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Rama Tulsi Live Plant | rama-tulsi-live-plant | Herbal & Medicinal Plants | True | Standard nursery plant\|GG-HRB-022\|49.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Red Hibiscus / Gudhal Live Plant | red-hibiscus-gudhal | Flowering Plants | True | Standard nursery plant\|GG-FLW-001\|99.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Rubber Plant | rubber-plant | Live Plants | False | NONE | NONE | missing_image, missing_variant |
| Sadabahar / Periwinkle Live Plant | sadabahar-periwinkle | Flowering Plants | True | Standard nursery plant\|GG-FLW-012\|59.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Snake Plant | snake-plant-sansevieria | Live Plants | True | Medium\|GG-IND-020\|249.00\|stock=0\|active=True | NONE | missing_image, zero_stock |
| Spinach Seeds (Palak) | spinach-seeds-palak | Seeds | False | NONE | NONE | missing_image, missing_variant |
| Sunflower Seeds | sunflower-seeds | Seeds | False | NONE | NONE | missing_image, missing_variant |
| Terracotta Clay Pot | terracotta-clay-pot | Pots & Planters | False | NONE | NONE | missing_image, missing_variant |
| Tomato Seeds | tomato-seeds | Seeds | False | NONE | NONE | missing_image, missing_variant |
| Watering Can | watering-can | Gardening Tools | False | NONE | NONE | missing_image, missing_variant |
| Zinnia Mixed Colour Live Plant | zinnia-mixed-colour | Flowering Plants | True | Standard nursery plant\|GG-FLW-014\|69.00\|stock=0\|active=True | NONE | missing_image, zero_stock |

## Website visibility findings

- Local active products require at least one active variant to appear in the product catalogue.
- The 25 active variants with stock 0 are not purchasable.
- 17 local products are inactive.
- 43 local products have no ProductImage record.
- Production visibility cannot be determined until Neon is read safely and production records are compared.

## Owner approval required

- No products were activated, inserted, deactivated, deleted, or restocked.
- No stock or price was changed.
- Approval is required to choose which local or production products to keep or remove.
- Approval is required for stock and price values before any data migration.

## Required for next step

Set a **read-only Neon DATABASE_URL** in the private local environment. Do not paste the URL or credentials into chat or reports.
The next audit must open PostgreSQL in a read-only transaction and export the same comparison without write operations.