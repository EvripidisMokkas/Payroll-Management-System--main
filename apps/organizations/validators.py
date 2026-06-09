"""Shared validation helpers for organization-owned business records."""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

# Payroll currently supports currencies with two-decimal minor units. Add currencies only
# after confirming downstream payroll, banking, and reporting support.
SUPPORTED_CURRENCIES = frozenset(
    {"AUD", "CAD", "CHF", "CNY", "EUR", "GBP", "INR", "JPY", "KES", "NGN", "NZD", "SGD", "USD", "ZAR"}
)

validate_identifier = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    message="Use letters, numbers, periods, underscores, slashes, or hyphens.",
)


def validate_currency(value):
    """Accept only explicitly supported uppercase ISO 4217 currency codes."""
    if value not in SUPPORTED_CURRENCIES:
        raise ValidationError("%(value)s is not a supported ISO 4217 currency code.", params={"value": value})
