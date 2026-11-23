# Production deployment

The existing deployment target is Vercel at <https://gach-ghar-team-jade.vercel.app/>. The deployment and Neon configuration still need to be verified in the Vercel project. No custom domain, payment account, email account, or persistent media provider has been confirmed here.

## 1. Runtime and dependencies

- Use Python 3.13 as selected by `.python-version` and install the pinned packages in an isolated virtual environment.
- Deploy the project source and migrations. Do not deploy `.env`, `db.sqlite3`, local backups, test reports, or a developer's `staticfiles/` output.
- Vercel's Django runtime detects the root `manage.py` and the configured WSGI/ASGI application; no custom `vercel.json` route or `/api` wrapper is required. With `STATIC_ROOT` configured, Vercel collects and serves static assets through its CDN. See [Vercel's Python runtime documentation](https://vercel.com/docs/functions/runtimes/python).
- `gunicorn` is included for Linux hosts that need a standalone WSGI server; Vercel's managed Python runtime does not need a separate Gunicorn start command.

For the existing Vercel project:

- Set the Python version to 3.13 (already recorded in `.python-version`).
- The `codex/gachghar-improvements` branch is excluded from automatic Vercel deployments in `vercel.json`; the `main` branch behavior is unchanged.
- Configure the required environment variables in Vercel's private project settings, including `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, exact allowed hosts and CSRF origins, and a PostgreSQL `DATABASE_URL` for Neon.
- Keep migrations as a reviewed release operation against the intended database after a verified backup; do not run migrations on every web request.
- Configure persistent object storage before relying on product or CMS uploads. Vercel function filesystems are not a durable media store.
- Verify the deployment's build log, runtime logs, Django checks, database backend, and representative customer routes after deployment.

For a standalone Render Web Service configured through its dashboard, use:

- Set the Python version to 3.13.x explicitly.
- Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- Start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- Configure `DATABASE_URL` to a managed PostgreSQL database. Do not rely on the service filesystem for SQLite or uploaded media persistence.

`render.yaml` is optional when build/start commands and environment are configured in the dashboard. Run reviewed migrations as a release/pre-deploy step after taking and verifying a database backup; do not put schema migrations in the build command.

## 2. Required private environment

Create environment variables in the host's secret manager or private `.env` file. Never commit or publish them.

| Variable | Production value |
|---|---|
| `DJANGO_DEBUG` | `False` |
| `DJANGO_SECRET_KEY` | A newly generated, private, high-entropy key; required in ALL environments (no dev fallback). Generate with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames only, without schemes |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated full HTTPS origins |
| `DATABASE_URL` | Managed PostgreSQL connection URL |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | The chosen transactional SMTP service |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Credentials from the selected Razorpay account; use test credentials before launch |
| `MEDIA_STORAGE_BACKEND` | Storage class path for production media (e.g. `storages.backends.s3boto3.S3Boto3Storage`). Leave empty for local filesystem. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_DEFAULT_ACL`, `AWS_S3_FILE_OVERWRITE` | AWS S3 credentials when `MEDIA_STORAGE_BACKEND` uses S3. |
| `AI_PROVIDER`, `AI_PROVIDER_API_KEY`, `AI_MODEL`, `AI_BASE_URL` | AI provider credentials for the AI Gardener assistant. Leave empty for basic mode. |
| `AI_RATE_LIMIT_PER_10_MIN`, `AI_DAILY_MESSAGE_LIMIT`, `AI_MAX_OUTPUT_TOKENS`, `AI_TIMEOUT_SECONDS` | AI usage cost controls. |

Set `DJANGO_SECURE_COOKIES=True`, `DJANGO_SECURE_SSL_REDIRECT=True`, and `DJANGO_HSTS_SECONDS=31536000` only when the production site is correctly served over HTTPS. Set `DJANGO_BEHIND_PROXY=True` only when the trusted proxy sets `X-Forwarded-Proto` correctly. Enable `DJANGO_HSTS_INCLUDE_SUBDOMAINS=True` only when every subdomain is HTTPS-only. HSTS preload is an explicit, long-lived domain decision; do not enable `DJANGO_HSTS_PRELOAD` without reviewing its requirements.

## Content-Security-Policy

A `SecurityHeadersMiddleware` (in `config/security_middleware.py`) enforces a Content-Security-Policy on every response. It allows self-hosted assets, Google Fonts, and the Razorpay Standard Checkout script and hosted frame (`checkout.razorpay.com` and `api.razorpay.com`). If you add third-party scripts, fonts, frames, or images, update the relevant CSP directive and test the integration before deploying.

For multiple application workers, use a shared cache for login and assistant rate limits. The built-in database cache is supported without an additional package:

```text
DJANGO_CACHE_BACKEND=django.core.cache.backends.db.DatabaseCache
DJANGO_CACHE_LOCATION=django_cache
```

Create its table with `python manage.py createcachetable` after configuring the production database. Use the same cache backend for all workers.

## 3. Database, static files, and media

Before each release, take a database backup and verify that it can be restored. Apply schema changes with:

```text
python manage.py migrate --noinput
```

Collect versioned static assets during release:

```text
python manage.py collectstatic --noinput
```

WhiteNoise serves collected static files. Product and CMS uploads are stored under `MEDIA_ROOT`; configure persistent storage and a web-server or object-storage route for `MEDIA_URL`. Back up uploaded media together with the database. Do not use the development media-serving route in production.

For local SQLite data, stop the application before copying `db.sqlite3` and the `media/` directory. For PostgreSQL, use the provider's supported `pg_dump`/restore procedure and test restores on a separate database. Never run destructive restore commands against the live database without explicit approval.

### Moving existing SQLite data to PostgreSQL

The SQLite database file cannot be used as a PostgreSQL database. If existing GachGhar records must move to PostgreSQL, rehearse the transfer against copies and an empty staging database first:

1. Stop application writes and make a protected copy of `db.sqlite3` and `media/`. Keep the originals unchanged and verify the SQLite copy with `PRAGMA integrity_check`.
2. Provision an empty PostgreSQL staging database and configure its `DATABASE_URL` only in the staging process/secret store. Use the same application revision and run `python manage.py migrate --noinput` against that empty target.
3. Point a separate process at the protected SQLite copy and export a fixture:

   ```text
   python manage.py dumpdata --natural-foreign --natural-primary --exclude=contenttypes --exclude=auth.permission --exclude=admin.logentry --exclude=sessions --output=/secure/path/gachghar-data.json
   ```

   This fixture contains customer and order data. Keep it private, outside Git, and remove it securely after the transfer has been verified.
4. Point a separate process at the staging PostgreSQL URL and load the fixture into the migrated, empty database:

   ```text
   python manage.py loaddata /secure/path/gachghar-data.json
   ```

5. Compare source and target counts for users, products, variants, stock movements, orders, order items, payments, shipments, coupons, and reviews. Reconcile order totals and stock balances, run the project tests, and verify every referenced media file is present in the chosen persistent/object storage.
6. Exercise checkout, invoice, account privacy, and shipment workflows in staging with test integrations only. Do not switch production traffic until the owner approves the verified transfer and a rollback plan; retain the untouched SQLite copy until then.

Do not run this procedure against the only copy of the database or import into a non-empty target. A successful `loaddata` alone is not proof that business totals, stock, permissions, or media were transferred correctly.

## 4. Release checks

Run these commands in the deployment environment before traffic is switched:

```text
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py test
```

Resolve security warnings that apply to the chosen domain and proxy. `check --deploy` reports warnings for `DEBUG=True`, insecure cookies, missing HTTPS redirect, HSTS, and HSTS subdomain/preload choices. The final two require a domain-owner decision about all subdomains and browser preload; do not silence those warnings by blindly enabling them.

Use the host's process manager to run `gunicorn config.wsgi:application`. Route HTTPS traffic to Gunicorn through the trusted proxy, restrict direct access to the application port, and retain application logs outside ephemeral container filesystems. The project logs failures to the configured Python console logger; connect that stream to the host's log service and alert on payment/webhook errors.

## 5. External setup still required

- Choose a domain and hosting provider and configure DNS, TLS certificates, firewall rules, and persistent media storage.
- Supply production PostgreSQL, SMTP, and Razorpay credentials privately.
- Configure Razorpay webhooks for `payment.captured` and `refund.processed`, and verify delivery in the Razorpay dashboard.
- Set actual delivery fees, free-shipping threshold, stock quantities, and product images from owner-approved data.
- Shiprocket/live carrier booking is intentionally deferred. Shipment tracking remains manual in Django Admin.

## 6. Actual-domain go-live checklist

Fill in the real values with the domain and hosting owner before proceeding. This checklist is preparation only; it does not authorize purchasing, changing credentials, or deploying.

- [ ] Domain: `________________`; canonical hostname: `________________`; `www` policy: `________________`.
- [ ] Hosting provider/plan and region: `________________`; person approving deployment: `________________`.
- [ ] DNS records point only to the chosen host; TLS certificate is active and renewal is configured.
- [ ] `DJANGO_ALLOWED_HOSTS` contains only the actual hostnames (no scheme); `DJANGO_CSRF_TRUSTED_ORIGINS` contains the exact HTTPS origins.
- [ ] A new production `DJANGO_SECRET_KEY` is held in the host's secret manager; `DJANGO_DEBUG=False`.
- [ ] HTTPS redirect and secure cookies are enabled. Configure the trusted proxy/header only if the host uses one. Enable HSTS only after HTTPS is verified; include subdomains/preload only after the domain owner confirms every affected hostname is HTTPS-only.
- [ ] Production PostgreSQL is provisioned; backup and restore have been tested; `DATABASE_URL` is private.
- [ ] The shared production cache is configured and `python manage.py createcachetable` has been run once if using Django's database cache.
- [ ] Persistent media storage and backups are configured; static assets are collected during release with `python manage.py collectstatic --noinput`.
- [ ] Gmail/transactional SMTP sender is verified; credentials are private and a controlled delivery test succeeds.
- [ ] Razorpay Test Mode checkout and webhook have passed on a non-production environment. Only after explicit launch approval, provision live keys and live webhook secret in the host secret manager.
- [ ] Owner-approved product images, prices, compare-at prices, and stock quantities are entered; do not publish unconfirmed catalog data.
- [ ] Review each current database value and owner action in [PRODUCT_DATA_REVIEW.csv](./PRODUCT_DATA_REVIEW.csv); do not treat current prices or stock as owner-approved until confirmed.
- [ ] CI/staging passes `python manage.py check`, `python manage.py check --deploy`, `python manage.py makemigrations --check --dry-run`, and `python manage.py test`.
- [ ] A database backup is taken immediately before release; migrations are reviewed and applied with `python manage.py migrate --noinput`.
- [ ] Gunicorn is behind the HTTPS proxy; direct application-port access is restricted; logs and payment/webhook failure alerts reach the host's monitoring system.
- [ ] Admin access uses named accounts and least-privilege groups; a rollback and incident contact are documented.
- [ ] Owner gives explicit approval before DNS cutover or production traffic is enabled.

The actual domain, provider, credentials, DNS, and launch approval have not been supplied; those entries remain intentionally blank.
