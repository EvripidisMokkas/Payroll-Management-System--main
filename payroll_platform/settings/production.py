"""Secure-by-default production settings."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

IS_PRODUCTION = True

if SECRET_KEY == "unsafe-development-key-change-me":  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")
if ALLOWED_HOSTS == ["localhost", "127.0.0.1"]:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set to production hosts.")
if not FIELD_ENCRYPTION_KEYS:  # noqa: F405
    raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS must be loaded from the production secret manager.")
if not DATA_FINGERPRINT_KEY:  # noqa: F405
    raise ImproperlyConfigured("DATA_FINGERPRINT_KEY must be loaded from the production secret manager.")
if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS must contain production HTTPS origins.")
if any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):  # noqa: F405
    raise ImproperlyConfigured("Production CSRF trusted origins must use HTTPS.")

DEBUG = False
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31_536_000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

RATE_LIMIT_ENABLED = True
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
SECURE_SSL_HOST = env("DJANGO_SECURE_SSL_HOST", default=None)  # noqa: F405

if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":  # noqa: F405
    DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = env(  # noqa: F405
        "DATABASE_SSLMODE", default="require"
    )
