from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        from .roles import ensure_role_groups

        post_migrate.connect(ensure_role_groups, dispatch_uid="accounts.ensure_role_groups")
