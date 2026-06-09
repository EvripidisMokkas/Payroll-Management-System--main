"""Authentication and identity models."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.security.fields import EncryptedTextField


class User(AbstractUser):
    """Platform identity with lockout and optional MFA state."""

    email = models.EmailField(unique=True)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = EncryptedTextField(blank=True)

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failed_login(self):
        self.failed_login_attempts += 1
        update_fields = ["failed_login_attempts"]
        if self.failed_login_attempts >= settings.ACCOUNT_LOCKOUT_THRESHOLD:
            self.locked_until = timezone.now() + timedelta(seconds=settings.ACCOUNT_LOCKOUT_DURATION)
            update_fields.append("locked_until")
        self.save(update_fields=update_fields)

    def clear_failed_logins(self):
        if self.failed_login_attempts or self.locked_until:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.save(update_fields=["failed_login_attempts", "locked_until"])
