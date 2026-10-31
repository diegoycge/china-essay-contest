"""Settings for the essay contest judging portal.

Everything deployment-specific is read from environment variables (see
.env.example). For local development a `.env` file next to manage.py is
loaded automatically.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    value = os.environ.get(name)
    return default if value in (None, "") else value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("SECRET_KEY must be set when DEBUG is off.")
    SECRET_KEY = "dev-only-insecure-key"

# Public address of the portal, used to build links in emails.
SITE_URL = env("SITE_URL", "http://localhost:8000").rstrip("/")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", SITE_URL)

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "portal",
]

if DEBUG:
    # Local development: serve CSS and JS through WhiteNoise with "always
    # re-check" headers. Django's own development file server sends no caching
    # instructions, so browsers kept showing a stale stylesheet after an edit.
    # (Production is unaffected: every file name there carries a content hash.)
    INSTALLED_APPS.insert(
        INSTALLED_APPS.index("django.contrib.staticfiles"), "whitenoise.runserver_nostatic"
    )
    WHITENOISE_USE_FINDERS = True
    WHITENOISE_AUTOREFRESH = True
    WHITENOISE_MAX_AGE = 0

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "portal.middleware.NoStoreMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "portal.context.portal",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "portal.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "full_name")},
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Sign-in throttling. Within the window, failures are capped per email + address
# pair (LOGIN_MAX_FAILURES), per address across all emails (x4, credential
# stuffing) and per email across all addresses (x5, distributed guessing).
LOGIN_MAX_FAILURES = int(env("LOGIN_MAX_FAILURES", "8"))
LOGIN_FAILURE_WINDOW_MINUTES = int(env("LOGIN_FAILURE_WINDOW_MINUTES", "15"))

# --- Internationalisation -------------------------------------------------
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("zh-hans", "简体中文")]
USE_I18N = True
USE_TZ = True
TIME_ZONE = env("TIME_ZONE", "America/New_York")

# --- Static and uploaded files -------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# Original submissions carry author identities. They are stored outside the
# web root and only ever streamed through an admin-only view.
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
MAX_ESSAY_FILE_MB = int(env("MAX_ESSAY_FILE_MB", "25"))
MAX_ESSAY_PAGES = int(env("MAX_ESSAY_PAGES", "60"))
# Each submitted PDF is rendered in a separate process under these limits, so
# a malformed or malicious file cannot stall or crash the web server.
PDF_RENDER_DPI = 175  # sharp on high-density screens at reading width
PDF_TIMEOUT_SECONDS = 90
PDF_CPU_SECONDS = 60
PDF_MEMORY_MB = int(env("PDF_MEMORY_MB", "2048"))
DATA_UPLOAD_MAX_NUMBER_FILES = 1000
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# --- Email -----------------------------------------------------------------
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_CONFIGURED = bool(EMAIL_HOST)
if EMAIL_CONFIGURED:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", not EMAIL_USE_SSL)
    EMAIL_TIMEOUT = 20
else:
    # Without SMTP the portal still works: invitation and reset links are shown
    # to the administrator to pass on by hand. Nothing is sent, and — on
    # purpose — nothing is printed either, so one-time links never reach the
    # server log.
    EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
# Self-service reset emails go out on a background thread so the page answers
# just as quickly for an unknown address as for a real one. Off under test.
EMAIL_IN_BACKGROUND = "test" not in sys.argv
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Essay Contest Judging <no-reply@localhost>")

# --- Security ----------------------------------------------------------------
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# Everything the pages load is served by the portal itself, so scripts from
# anywhere else (or injected inline) are refused by the browser. Inline style
# attributes are allowed; inline scripts and event handlers are not.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)

SECURE_COOKIES = env_bool("SECURE_COOKIES", not DEBUG)
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
# Trust X-Forwarded-* headers only when a reverse proxy (Caddy, nginx) sets them.
BEHIND_PROXY = env_bool("BEHIND_PROXY", not DEBUG)
if BEHIND_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(env("HSTS_SECONDS", "0"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "filters": {"one_time_links": {"()": "portal.logfilter.RedactOneTimeLinks"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "plain",
            "filters": ["one_time_links"],
        }
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
