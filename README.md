# GachGhar

Single-vendor online plant nursery and gardening store for India. Built with Python, Django, Django ORM, Django Templates, HTML5, CSS3 and vanilla JavaScript. SQLite for local development, PostgreSQL for production.

Status: see `PROJECT_STATE.md` for what is built, what is verified, and what remains.

## Project layout

```
GachGhar/
├── manage.py
├── requirements.txt          pinned dependencies
├── .env.example              variable names with placeholder values only
├── config/                   settings (env driven), urls, wsgi, asgi
├── accounts/                 customers: login (email or phone), registration, profile, addresses, order history
├── store/                    catalogue, cart, wishlist, checkout, orders, CMS, admin, AI assistant service
│   ├── models.py  services.py  views.py  commerce.py  admin.py  ai_services.py  tests.py
│   └── templatetags/store_tags.py   the |inr price filter
├── templates/                base.html, partials/ (header, drawers, cards), store/, accounts/
└── static/
    ├── css/main.css          design tokens in :root (colours, radii, fonts)
    ├── js/main.js            drawers, cart, wishlist, gallery, assistant (vanilla JS)
    └── assets/images/        branding/ (official logo and derivatives), reference/ (hero image)
```

## First setup (Windows, VS Code)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Set DJANGO_SECRET_KEY in .env using the generation command documented there.
python manage.py migrate
python manage.py check
python manage.py test
python manage.py createsuperuser
python manage.py runserver
```

Then open http://127.0.0.1:8000/ for the store and http://127.0.0.1:8000/admin/ for the admin panel.

The source includes the migrations needed by the current models. Run `makemigrations` only after changing models, and commit any generated migrations with the related code changes.

## Configuration

Secrets and environment values go in `.env` (never committed) or real environment variables. See `.env.example` for every name.

| Area | Where to change it |
| --- | --- |
| Logo | Admin > Site settings > logo override (blank = official logo) |
| Colours, fonts, spacing | `static/css/main.css`, `:root` block |
| Navigation categories | Admin > Categories (top level and children); the header and mega menu follow them |
| Homepage sections, order, on/off | Admin > Home sections |
| Hero text and image, announcement bar, footer, contact | Admin > Site settings |
| Products, variants, prices, images | Admin > Products |
| Stock | Admin > Stock movements (the only way stock changes; history is kept) |
| Cash on delivery, shipping fee, free-shipping threshold | Admin > Site settings |
| Policies, about, contact page | Admin > Static pages (unpublished pages show as not found) |
| Plant care guides | Admin > Guides |
| Customer reviews | Admin > Reviews (approve to publish) |
| Payment gateway, AI provider | See `docs/OPERATIONS.md` and `docs/AI_CONFIGURATION.md` |

## Testing

```powershell
python manage.py test
```

The suites cover catalogue visibility, reviews, invoices, delivery rules, shipping notifications, admin order actions, stock and cart rules, checkout, ownership checks, and authentication. See `PROJECT_STATE.md` for the latest verification results and remaining live-environment checks.

## Security notes

- Passwords use Argon2 (with PBKDF2 as fallback), with Django's validators.
- Login is throttled per identifier after repeated failures.
- Customer order and address pages use ownership checks, and return 404 for other customers' records.
- Cart prices, stock, shipping and totals are calculated on the server. The browser's values are never trusted.
- Checkout uses a one-time token to prevent duplicate orders on double submit.
- Production mode (`DJANGO_DEBUG=False`) enables secure cookies, HTTPS redirect and HSTS settings, controlled by env variables. Run `python manage.py check --deploy` before going live.
- Content-Security-Policy is enforced by `config/security_middleware.py`; it allows Razorpay Standard Checkout's script and hosted frame while keeping the rest of the policy restrictive.
- The application is not claimed to be hack-proof. Review it with OWASP guidance before launch.

## Deployment

The project has an existing Vercel deployment at <https://gach-ghar-team-jade.vercel.app/>. Its current availability and production configuration must be checked in Vercel; a URL in project notes is not proof that the latest code, Neon database, or persistent media are working. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for Vercel and alternate-host release steps. Production requires PostgreSQL, and uploaded media must use persistent storage; Django serves local media only in debug mode.
