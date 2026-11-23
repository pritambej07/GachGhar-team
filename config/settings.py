"""GachGhar settings. Sensitive values come from environment variables (see .env.example)."""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # optional local file; real environment variables take priority


def env(name, default=""):
    """Empty values (e.g. 'DATABASE_URL=' in .env) fall back to the default."""
    return os.environ.get(name) or default


def env_bool(name, default=False):
    return env(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set in all environments. "
        "Generate one with: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    )
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "accounts",
    "store.apps.StoreConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "config.security_middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "store.context_processors.site_context",
            ],
        },
    },
]

# SQLite by default; set DATABASE_URL (e.g. postgres://user:pass@host/db) for production.
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
    )
}
if not DEBUG and DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    raise ImproperlyConfigured(
        "Production requires DATABASE_URL pointing to PostgreSQL; SQLite is not persistent on serverless hosting."
    )

AUTH_USER_MODEL = "auth.User"
AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailOrPhoneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Media storage - local filesystem by default. For production with object storage
# In production, Cloudinary is required because Vercel's filesystem is ephemeral.
CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = env("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = env("CLOUDINARY_API_SECRET")
CLOUDINARY_CONFIGURED = all((CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET))
if not DEBUG and not CLOUDINARY_CONFIGURED:
    raise ImproperlyConfigured(
        "Production requires CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET "
        "for persistent media storage."
    )

if CLOUDINARY_CONFIGURED:
    import cloudinary

    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )

if not DEBUG:
    MEDIA_STORAGE_BACKEND = "store.storage.CloudinaryMediaStorage"
else:
    MEDIA_STORAGE_BACKEND = env("MEDIA_STORAGE_BACKEND", "") or (
        "store.storage.CloudinaryMediaStorage" if CLOUDINARY_CONFIGURED else "django.core.files.storage.FileSystemStorage"
    )
STORAGES = {
    "default": {
        "BACKEND": MEDIA_STORAGE_BACKEND or "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "store:home"

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@localhost")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_REFERRER_POLICY = "same-origin"

if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS")
    SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if env_bool("DJANGO_BEHIND_PROXY") else None

# Business and integration settings (non-secret).
SITE_NAME = "GachGhar"
CART_MAX_QUANTITY = 20
LOGIN_MAX_FAILURES = 10
# AI Gardener. Empty provider/key/model = basic mode only; the store keeps working. Secrets only in .env.
AI_PROVIDER = env("AI_PROVIDER", "")  # "openai" (also OpenAI-compatible APIs via AI_BASE_URL) or "anthropic"
AI_PROVIDER_API_KEY = env("AI_PROVIDER_API_KEY", "")
AI_MODEL = env("AI_MODEL", "")  # exact model id from your provider's dashboard; deliberately has no default
AI_BASE_URL = env("AI_BASE_URL", "")  # optional override for OpenAI-compatible providers
AI_RATE_LIMIT_PER_10_MIN = int(env("AI_RATE_LIMIT_PER_10_MIN", "20"))
AI_DAILY_MESSAGE_LIMIT = int(env("AI_DAILY_MESSAGE_LIMIT", "100"))  # per signed-in user or IP; caps provider cost
AI_MAX_OUTPUT_TOKENS = int(env("AI_MAX_OUTPUT_TOKENS", "600"))
AI_TIMEOUT_SECONDS = int(env("AI_TIMEOUT_SECONDS", "25"))

CACHES = {
    "default": {
        "BACKEND": env("DJANGO_CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": env("DJANGO_CACHE_LOCATION", "gachghar-local"),
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "WARNING")},
}

# Razorpay payment gateway
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", "")
