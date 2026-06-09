"""Central service-layer authorization; never trust a caller-supplied tenant alone."""

from django.core.exceptions import PermissionDenied

from .models import OrganizationMembership, OrganizationRole

ROLE_ACTIONS = {
    OrganizationRole.ADMINISTRATOR: {
        "organization.manage",
        "employee.read",
        "employee.write",
        "client.read",
        "client.write",
        "payroll.read",
        "payroll.write",
        "payroll.delete",
        "audit.read",
        "audit.annotate",
        "audit.export",
        "document.read",
        "document.read_sensitive",
        "document.write",
        "document.manage_retention",
        "document.export",
        "document.redact",
        "compensation.approve",
        "compensation.apply",
        "compensation.read",
        "finance.read",
        "finance.forecast",
        "analytics.read",
        "risk.read",
        "risk.manage",
    },
    OrganizationRole.PAYROLL_OPERATOR: {
        "employee.read",
        "employee.write",
        "client.read",
        "payroll.read",
        "payroll.write",
        "finance.read",
        "analytics.read",
        "document.read",
        "document.read_sensitive",
        "document.write",
    },
    OrganizationRole.EMPLOYEE: {"payroll.read", "payroll.read_own", "finance.read", "analytics.read", "document.read"},
    OrganizationRole.AUDITOR: {
        "employee.read",
        "payroll.read",
        "audit.read",
        "audit.annotate",
        "finance.read",
        "analytics.read",
        "risk.read",
        "audit.export",
        "document.read",
        "document.read_sensitive",
        "document.export",
    },
    OrganizationRole.CLIENT: {"payroll.read", "audit.read", "finance.read", "analytics.read", "document.read"},
}


def membership_for(user, organization):
    if not user.is_authenticated:
        return None
    return OrganizationMembership.objects.filter(user=user, organization=organization, is_active=True).first()


def authorize(user, organization, action):
    if user.is_superuser:
        return None
    membership = membership_for(user, organization)
    if not membership or action not in ROLE_ACTIONS[membership.role]:
        raise PermissionDenied("You are not authorized for this organization or action.")
    return membership


def assign_membership(actor, user, organization, role):
    """The only supported membership mutation path; prevents role escalation."""
    authorize(actor, organization, "organization.manage")
    membership, _ = OrganizationMembership.objects.update_or_create(
        user=user, organization=organization, defaults={"role": role, "is_active": True}
    )
    return membership
