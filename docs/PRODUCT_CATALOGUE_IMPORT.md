# Product catalogue import

The owner-supplied 26-product list is encoded in the `import_catalogue` Django management command. It uses the existing `Product`, `ProductVariant`, `Category`, and stock-ledger models.
The current database match, price, stock, SKU, and image review is in [PRODUCT_CATALOGUE_REVIEW.csv](./PRODUCT_CATALOGUE_REVIEW.csv).
The source-image scan found one existing product photo (`media/products/images.jpg`) already attached to the plastic nursery pot, plus only branding and a generic greenhouse reference image. No image was suitable and rights-verified for the remaining products, so no image files were added or reassigned.

## Safe workflow

1. Review product names, prices, categories, and specification text in the command.
2. Make a separate copy of the current database and verify the copy before any import.
3. Run a read-only preview:

   ```powershell
   py manage.py import_catalogue
   ```

4. Resolve every ambiguous match and provide an owner-approved SKU, actual stock quantity, and an image with confirmed usage rights for each product that needs them.
5. Only after approving the preview and verifying a fresh database backup, explicitly apply:

   ```powershell
   py manage.py import_catalogue --apply --backup-verified
   ```

The command is dry-run by default. Applying it reuses matching categories and products, updates only unambiguous product details and explicitly supplied prices, and creates unmatched products as inactive stubs. It does not create variants without owner-provided SKUs, change stock, assign images, or alter existing comparison prices. Different pack sizes, ambiguous products, and slug conflicts are skipped for owner review. Re-running the command does not create duplicate categories or products.

New stubs are not visible in the storefront until an administrator adds a real variant/SKU and stock through the existing inventory workflow, supplies an image if available, and activates the product.
