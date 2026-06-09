"""Field-level encryption and deterministic fingerprints.

Production keys must come from the deployment secret manager. Ciphertext is prefixed
with a version marker so plaintext legacy values can be read and migrated safely.
"""

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

CIPHERTEXT_PREFIX = "enc:v1:"


def _development_key():
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode()


def configured_keys():
    keys = list(getattr(settings, "FIELD_ENCRYPTION_KEYS", []))
    if not keys and not getattr(settings, "IS_PRODUCTION", False):
        keys = [_development_key()]
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS must be supplied by the production secret manager.")
    return keys


def _cipher():
    try:
        return MultiFernet([Fernet(key.encode()) for key in configured_keys()])
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS contains an invalid Fernet key.") from exc


def encrypt(value):
    if value in (None, "") or str(value).startswith(CIPHERTEXT_PREFIX):
        return value
    token = _cipher().encrypt(str(value).encode()).decode()
    return f"{CIPHERTEXT_PREFIX}{token}"


def decrypt(value):
    if value in (None, "") or not str(value).startswith(CIPHERTEXT_PREFIX):
        return value
    try:
        return _cipher().decrypt(str(value)[len(CIPHERTEXT_PREFIX) :].encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Encrypted value could not be decrypted with an active key.") from exc


def fingerprint(value):
    """Return a non-reversible lookup fingerprint; never use it for authentication."""
    key = getattr(settings, "DATA_FINGERPRINT_KEY", "")
    if not key and not getattr(settings, "IS_PRODUCTION", False):
        key = settings.SECRET_KEY
    if not key:
        raise ImproperlyConfigured("DATA_FINGERPRINT_KEY must be supplied by the production secret manager.")
    return hmac.new(key.encode(), str(value).strip().encode(), hashlib.sha256).hexdigest()
