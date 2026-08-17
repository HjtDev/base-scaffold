"""Django settings for this project.

A single, standard Django settings file — no settings package, no composer, no filesystem
scanning. Values come from `.env` via `python-decouple`. See BASE-DESIGN.md §4.3.

Installed app packages are wired in by copy-pasting the block from that app's own
`README.md` — `INSTALLED_APPS`, `MIDDLEWARE`, `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`
entries, and its own settings dict — into the marked spots below. There is no dynamic
merge step. See INTEGRATION-GUIDE.md §2.

Deliberately absent: any authentication configuration. Auth is its own installed app
package, never part of this scaffold — see BASE-DESIGN.md §3.
"""

from pathlib import Path

from decouple import Csv, config

from config.logging import build_logging_config

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------- core
DEBUG = config("DEBUG", default=False, cast=bool)
SECRET_KEY = config("SECRET_KEY")  # no default — fail loudly
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())
FERNET_KEY = config("FERNET_KEY")
SENTRY_DSN = config("SENTRY_DSN", default="")

# ---------------------------------------------------------------------------- apps
INSTALLED_APPS = [
    # jazzmin MUST precede django.contrib.admin — it overrides the admin templates via
    # Django's app-directories loader, which resolves to the first match in this list.
    # Reversed, the admin still renders, just silently unthemed — see CORRECTIONS.md #4.
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "django_celery_beat",
    "core",
    # ---- installed app packages get added here, one line each, per their own README
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.logging.RequestIDMiddleware",  # before anything that logs, after security
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # ---- installed app packages append their middleware here, per their own README
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Host templates win over an app package's — see INTEGRATION-GUIDE.md §5.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------- database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB"),
        "USER": config("POSTGRES_USER"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": config("POSTGRES_HOST", default="db"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": config("CONN_MAX_AGE", default=60, cast=int),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------- cache
REDIS_URL = config("REDIS_URL")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# ---------------------------------------------------------------------------- i18n
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]

# ---------------------------------------------------------------------------- static/media
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Host static dir first — same override ordering as TEMPLATES, see INTEGRATION-GUIDE.md §5.
STATICFILES_DIRS: list[Path] = []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------- DRF / schema
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {},  # app installs add their own scopes here
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API",
    "DESCRIPTION": "",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---------------------------------------------------------------------------- admin theme
JAZZMIN_SETTINGS = {
    "site_title": "Admin",
    "site_header": "Admin",
    "welcome_sign": "Admin",
    # Installed app packages can suggest an icon for their models here, per their own
    # README — they cannot register into this dict themselves. See APP-DESIGN.md §5.
    "icons": {},
}

# ---------------------------------------------------------------------------- CORS
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())

# ---------------------------------------------------------------------------- security
# Env-driven, defaulting to "secure unless DEBUG says otherwise". See CORRECTIONS.md #3
# for why SECURE_HSTS_SECONDS is the one exception that does NOT inherit that default.
_SECURE_DEFAULT = not DEBUG
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=_SECURE_DEFAULT, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=_SECURE_DEFAULT, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=_SECURE_DEFAULT, cast=bool)
# Defaults to 0 in every environment, including prod: a year of HSTS is effectively
# irreversible for the domain and every subdomain, so turning it on is a deliberate,
# explicit act (backend/.env.prod.example sets 31536000), never an inherited default.
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
# Only trust X-Forwarded-Proto when a proxy is known to sit in front — trusting it
# unconditionally is a spoofing vector the moment the container is reachable directly.
TRUST_PROXY_SSL_HEADER = config("TRUST_PROXY_SSL_HEADER", default=_SECURE_DEFAULT, cast=bool)
if TRUST_PROXY_SSL_HEADER:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # must stay JS-readable — the Next.js frontend sends it as a header
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------------------- celery
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# No CELERY_BEAT_SCHEDULE here — periodic tasks are host-created PeriodicTask rows,
# preferably via a data migration in core/, never auto-registered. See BASE-DESIGN.md §6.

# ---------------------------------------------------------------------------- logging
LOGGING = build_logging_config(debug=DEBUG)  # from config/logging.py, see §3

# ---------------------------------------------------------------------------- sentry
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    def _traces_sampler(sampling_context: dict) -> float:
        # Keep /healthz/ out of the transaction sample — it's polled every 30s by every
        # compose healthcheck and carries no useful signal. See BASE-DESIGN.md §8.2.
        asgi_scope = sampling_context.get("asgi_scope", {})
        if asgi_scope.get("path", "").rstrip("/") == "/healthz":
            return 0.0
        return config("SENTRY_TRACES_SAMPLE_RATE", default=0.1, cast=float)

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration(), RedisIntegration()],
        traces_sampler=_traces_sampler,
        send_default_pii=False,
    )

# ---------------------------------------------------------------------------- startup validation
from config import checks  # noqa: F401,E402
