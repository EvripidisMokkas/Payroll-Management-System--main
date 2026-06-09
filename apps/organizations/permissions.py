"""Django REST Framework permission adapter for organization-aware views."""

from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


class OrganizationActionPermission(BasePermission):
    def has_permission(self, request, view):
        try:
            view.get_organization()
        except (KeyError, PermissionDenied):
            return False
        return True
