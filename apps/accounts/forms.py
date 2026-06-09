from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from .mfa import verify_totp


class MFAAuthenticationForm(AuthenticationForm):
    mfa_token = forms.CharField(required=False, max_length=6)

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_locked():
            raise ValidationError("This account is temporarily locked.", code="locked")
        if user.mfa_enabled and not verify_totp(user.mfa_secret, self.cleaned_data.get("mfa_token")):
            raise ValidationError("A valid multi-factor authentication code is required.", code="mfa_required")
