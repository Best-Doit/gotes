import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("GOTES_DATA_DIR", os.environ.get("GOTS_DATA_DIR", BASE_DIR / ".data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def env_bool(name, default=False):
    return os.environ.get(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [item.strip() for item in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if item.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.SuperuserAdminOnlyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if not DEBUG:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "core.context_processors.navigation",
        ],
    },
}]
WSGI_APPLICATION = "config.wsgi.application"

if os.environ.get("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "gotes"),
            "USER": os.environ.get("POSTGRES_USER", "gotes"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ["POSTGRES_HOST"],
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.environ.get("POSTGRES_CONN_MAX_AGE", "60")),
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {"sslmode": os.environ.get("POSTGRES_SSLMODE", "prefer")},
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATA_DIR / "db.sqlite3", "OPTIONS": {"timeout": 20}}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-bo"
TIME_ZONE = "America/La_Paz"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}
MEDIA_ROOT = Path(os.environ.get("GOTES_MEDIA_ROOT", os.environ.get("GOTS_MEDIA_ROOT", DATA_DIR / "media")))
MEDIA_URL = "/archivos-no-publicos/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "core.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024

GOTES_PUBLIC_URL = os.environ.get("GOTES_PUBLIC_URL", os.environ.get("GOTS_PUBLIC_URL", "http://localhost:8000")).rstrip("/")
EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("DJANGO_EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = int(os.environ.get("DJANGO_EMAIL_TIMEOUT", "15"))
_configured_from_email = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "").strip()
DEFAULT_FROM_EMAIL = _configured_from_email or (f"GOTES <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "GOTES <no-reply@example.com>")
EMAIL_OUTBOX_MAX_ATTEMPTS = int(os.environ.get("GOTES_EMAIL_MAX_ATTEMPTS", os.environ.get("GOTS_EMAIL_MAX_ATTEMPTS", "5")))
EMAIL_OUTBOX_PROCESSING_TIMEOUT_MINUTES = int(os.environ.get("GOTES_EMAIL_PROCESSING_TIMEOUT_MINUTES", os.environ.get("GOTS_EMAIL_PROCESSING_TIMEOUT_MINUTES", "15")))
EVIDENCE_MAX_FILE_SIZE_MB = int(os.environ.get("GOTES_EVIDENCE_MAX_FILE_SIZE_MB", "5"))

CSRF_TRUSTED_ORIGINS = [
    item.strip()
    for item in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if item.strip()
]
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", False)
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
if env_bool("DJANGO_TRUST_PROXY_HEADERS", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
