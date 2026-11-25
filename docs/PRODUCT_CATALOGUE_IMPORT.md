# Product catalogue import

`import_catalogue` is scoped to the 15 products in the current production plan and the five existing categories: Indoor Plants, Seeds, Fertilizers & Soil, Pots & Planters, and Gardening Tools. It recognizes known category and product aliases so an existing record is not duplicated. It refuses to apply if one of the required categories is missing or ambiguous.

The command is a read-only preview by default:

```powershell
python manage.py import_catalogue
```

Review the complete match report against the verified Production database. The preview shows existing matches and conflicts without writing. It must not be run against Preview or a local database as a substitute for checking Production.

Applying requires a separately verified recovery point and the explicit acknowledgement flag:

```powershell
python manage.py import_catalogue --apply --backup-verified
```

The command preserves matching products and every existing category. It creates only unmatched product records as inactive stubs with the planned price, a generated planning SKU, and the model's zero-stock default. It does not add categories, change existing product names, descriptions, categories, prices, SKUs, stock, or images, and it does not create stock movements. New stubs stay off the storefront until an owner verifies real stock and a suitable image, then activates them in Admin. Never apply until the Production target, category matches, and recovery point have been verified.

The separate `seed_gachghar_catalogue` command is for the broader 26-product local catalogue; it is not the command for this 15-product Production plan.

The project currently has no complete supplied image set for these 15 planned products. A prior repository scan found one existing product photo attached to the plastic nursery pot, plus branding and a generic greenhouse image. Do not reuse unrelated imagery or invent product photos. Confirm image ownership and suitability before adding assets.
