"""Shared Django settings for every environment."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]
env = environ.Env(
    DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, []),
    DATABASE_CONN_MAX_AGE=(int, 60),
    DOCUMENT_MAX_UPLOAD_BYTES=(int, 10 * 1024 * 1024),
    FIELD_ENCRYPTION_KEYS=(list, []),
    RATE_LIMIT_ENABLED=(bool, False),
    API_RATE_LIMIT=(int, 300),
    AUTH_RATE_LIMIT=(int, 10),
    RATE_LIMIT_WINDOW_SECONDS=(int, 60),
    LEGAL_REVIEW_APPROVED_JURISDICTIONS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-development-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = [
    "django_filters",
    "rest_framework",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
]
LOCAL_APPS = [
    "apps.security",
    "apps.accounts",
    "apps.organizations",
    "apps.employees",
    "apps.compensation",
    "apps.clients",
    "apps.payroll",
    "apps.taxation",
    "apps.finance",
    "apps.documents",
    "apps.auditing",
    "apps.analytics",
    "apps.risk",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.security.middleware.RateLimitMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.SessionIdleTimeoutMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.security.middleware.SecurityHeadersMiddleware",
]
ROOT_URLCONF = "payroll_platform.urls"
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
            ],
        },
    }
]
WSGI_APPLICATION = "payroll_platform.wsgi.application"
ASGI_APPLICATION = "payroll_platform.asgi.application"

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgresql://payroll:payroll@localhost:5432/payroll",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env("DATABASE_CONN_MAX_AGE")
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "private": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": BASE_DIR / "private-media"},
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DOCUMENT_MAX_UPLOAD_BYTES = env("DOCUMENT_MAX_UPLOAD_BYTES")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Payroll Platform API",
    "DESCRIPTION": "API for payroll, workforce, finance, and compliance workflows.",
    "VERSION": "1.0.0",
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="django-db")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {process:d} {thread:d} {message}", "style": "{"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {"django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False}},
}

AUTHENTICATION_BACKENDS = ["apps.accounts.backends.LockoutModelBackend"]
ACCOUNT_LOCKOUT_THRESHOLD = env.int("ACCOUNT_LOCKOUT_THRESHOLD", default=5)
ACCOUNT_LOCKOUT_DURATION = env.int("ACCOUNT_LOCKOUT_DURATION", default=900)
SESSION_IDLE_TIMEOUT = env.int("SESSION_IDLE_TIMEOUT", default=1800)
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=28800)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"

# Security services. Production must supply these values through its secret manager.
IS_PRODUCTION = False
FIELD_ENCRYPTION_KEYS = env("FIELD_ENCRYPTION_KEYS")
DATA_FINGERPRINT_KEY = env("DATA_FINGERPRINT_KEY", default="")
RATE_LIMIT_ENABLED = env("RATE_LIMIT_ENABLED")
API_RATE_LIMIT = env("API_RATE_LIMIT")
AUTH_RATE_LIMIT = env("AUTH_RATE_LIMIT")
RATE_LIMIT_WINDOW_SECONDS = env("RATE_LIMIT_WINDOW_SECONDS")
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
)
CSRF_COOKIE_SAMESITE = "Strict"
PASSWORD_RESET_TIMEOUT = 3600
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
LEGAL_REVIEW_APPROVED_JURISDICTIONS = env("LEGAL_REVIEW_APPROVED_JURISDICTIONS")
