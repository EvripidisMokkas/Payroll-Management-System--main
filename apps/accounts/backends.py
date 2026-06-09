"""Authentication backend that applies per-account lockout."""

from django.contrib.auth.backends import ModelBackend

from .models import User


class LockoutModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        lookup = username or kwargs.get(User.USERNAME_FIELD)
        try:
            user = User.objects.get(username=lookup)
        except User.DoesNotExist:
            return super().authenticate(request, username=username, password=password, **kwargs)
        if user.is_locked():
            return None
        authenticated = super().authenticate(request, username=username, password=password, **kwargs)
        if authenticated:
            user.clear_failed_logins()
        elif user.is_active:
            user.register_failed_login()
        return authenticated
