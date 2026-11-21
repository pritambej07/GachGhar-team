# GachGhar project state

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
