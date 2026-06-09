"""Role-based visibility rules for financial source records."""

from apps.organizations.models import OrganizationRole
from apps.organizations.services import membership_for

from .models import AccountCategory

ROLE_CATEGORIES = {
    OrganizationRole.ADMINISTRATOR: set(AccountCategory.values),
    OrganizationRole.AUDITOR: set(AccountCategory.values),
    OrganizationRole.CLIENT: {
        AccountCategory.REVENUE,
        AccountCategory.OPERATING_COST,
        AccountCategory.INSURANCE_PREMIUM,
        AccountCategory.INSURANCE_CLAIM,
    },
    OrganizationRole.PAYROLL_OPERATOR: {AccountCategory.REVENUE, AccountCategory.PAYROLL_COST},
    OrganizationRole.EMPLOYEE: set(),
}


def visible_categories(user, organization):
    if user.is_superuser:
        return set(AccountCategory.values)
    membership = membership_for(user, organization)
    return ROLE_CATEGORIES.get(membership.role, set()) if membership else set()
