"""Admin registrations for account management."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class PlatformUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Security", {"fields": ("mfa_enabled", "mfa_secret", "failed_login_attempts", "locked_until")}),
    )
    readonly_fields = ("failed_login_attempts", "locked_until")
