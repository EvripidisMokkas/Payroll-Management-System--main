"""Reusable mixins that fail closed for cross-tenant requests."""

from typing import Any

from django.core.exceptions import PermissionDenied

from .models import Organization
from .services import authorize


class OrganizationAccessMixin:
    kwargs: dict[str, Any]
    request: Any
    organization_url_kwarg = "organization_id"
    required_action = None

    def get_organization(self):
        try:
            organization = Organization.objects.get(pk=self.kwargs[self.organization_url_kwarg], is_active=True)
        except Organization.DoesNotExist as exc:
            raise PermissionDenied("Unknown or unauthorized organization.") from exc
        authorize(self.request.user, organization, self.required_action)
        return organization

    def get_queryset(self):
        return super().get_queryset().for_user(self.request.user).for_organization(self.get_organization())  # type: ignore[misc]
