"""Fail-closed production gate for regulated calculations."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def require_approved_jurisdiction(jurisdiction_code, calculation_type):
    if not getattr(settings, "IS_PRODUCTION", False):
        return
    approvals = set(getattr(settings, "LEGAL_REVIEW_APPROVED_JURISDICTIONS", []))
    if jurisdiction_code not in approvals:
        message = (
            f"{calculation_type} calculations for {jurisdiction_code} require documented "
            "jurisdiction-specific legal and accounting approval."
        )
        raise ImproperlyConfigured(message)
