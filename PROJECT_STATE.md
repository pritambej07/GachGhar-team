# GachGhar project state

## Verification snapshot — 23 November 2026

- This checkout is on the isolated `codex/gachghar-improvements` branch. The existing `main` branch was clean before work started.
- `python manage.py check`: passed.
- `python manage.py makemigrations --check --dry-run`: passed; no missing migrations.
- `python manage.py test`: passed, 210 tests after adding catalogue-seeder and image-fallback coverage.
- `python manage.py collectstatic --noinput`: passed; 6 files copied and 132 unchanged.
- `python -m pip check`, JavaScript syntax checks, and `git diff --check`: passed.
- `python manage.py check --deploy` still reports five warnings because this is the local debug environment; production HTTPS and cookie settings must be verified in Vercel rather than inferred from `.env`.
- The local `.env` does not configure `DATABASE_URL`, so this checkout uses SQLite. This says nothing about Vercel's environment or Neon; neither is connected to this local session.
- The existing deployment URL supplied in project notes is <https://gach-ghar-team-jade.vercel.app/>. Live availability and production behavior were not verified from this session.
- The new production settings guard rejects SQLite when `DJANGO_DEBUG=False`; a targeted startup check confirmed the guard.
- The safe catalogue command is `python manage.py seed_gachghar_catalogue`. It previews and rolls back by default; `--apply` is required to write. Its tests confirm repeatability, active flags, preservation of existing product data and ledger stock, and no image or stock creation. A local preview identified three category mismatches and skipped them; no local database changes were saved.
- Product cards and product detail pages now show a branded initial fallback when a stored product-image URL fails; a template regression test covers the detail-page markup. This does not supply or host product photographs.

## Verification snapshot — 21 November 2026

- `python manage.py check`: passed with no issues.
- `python manage.py makemigrations --check --dry-run`: passed; no missing migrations.
- `python manage.py test`: passed, 206 tests.
- `python manage.py test store.test_payment_views`: passed, 32 tests.
- `python manage.py test accounts.tests_address`: passed, 9 tests.
- `python -m pip check`: passed; no broken requirements.
- `node --check` passed for `static/js/search.js`, `static/js/main.js`, and `static/js/assistant.js`.
- SQLite integrity checks returned `ok` for both `db.sqlite3` and `db_backup_before_migrate.sqlite3`. Neither database was modified by these checks or the test runs.

## Payment and external-service limits

- Razorpay is configured through private environment variables and the application uses Razorpay Standard Checkout, INR amounts, server-side signature verification, guest-session ownership checks, and webhook verification. Keep local credentials in Test Mode.
- Automated tests cover payment-page access, order creation, signature checks, callbacks, webhooks, and duplicate processing. A real Razorpay Test Mode transaction and live UPI app flow were not exercised in this environment.
- Browser automation was unavailable, so the Razorpay overlay and visual layout have not been verified in a real browser here. The local server still needs a manual checkout smoke test.
- SMTP delivery, production database migration, hosting, DNS, TLS, and deployment were not exercised.
- `python manage.py check --deploy` should be run for the actual HTTPS deployment. Its local-mode warnings depend on the production domain, proxy, and HTTPS configuration; do not silence them by changing local debug settings.

## Implemented project areas

The current source includes the AI Gardener assistant and provider adapters, customer reviews, coupons, address management, invoice downloads, order/shipment tracking fields and admin actions, delivery rules, catalog search, Razorpay checkout, CSP/security headers, and database migrations. See the application code, tests, and `docs/` for details.

## Local startup

Use the existing private `.env`; do not overwrite it with `.env.example`. Install the pinned requirements in a virtual environment, then run:

```powershell
python manage.py check
python manage.py migrate
python manage.py runserver
```

Use `python manage.py test` for the full automated suite. Do not run `makemigrations` unless model changes require a reviewed migration.

## Remaining owner actions

- Open checkout in a local browser and verify the Razorpay overlay loads and displays UPI with the test account. Use only Test Mode credentials and test instruments.
- Configure and verify Razorpay webhook events in the Test Mode dashboard if webhook delivery is being exercised.
- Choose hosting/domain, configure HTTPS and production-only settings, verify backups/restores, and confirm owner-approved catalog content before deployment.
- Live payments and production deployment require a separate explicit launch decision; this snapshot does not authorize either.
