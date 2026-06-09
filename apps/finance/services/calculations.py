"""Transparent finance calculations backed by organization-scoped ledger records."""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum

from apps.finance.models import AccountCategory, FinancialMetric, InsurancePolicy, LedgerEntry, MetricType

ZERO = Decimal("0")
MONEY = Decimal("0.01")
RATIO = Decimal("0.0001")
ROUNDING_POLICY = ROUND_HALF_UP


def money(value):
    """Round a monetary result to cents using the documented finance policy."""
    return Decimal(str(value)).quantize(MONEY, rounding=ROUNDING_POLICY)


def ratio(value):
    """Round percentage metrics to four decimal places using the finance policy."""
    return Decimal(str(value)).quantize(RATIO, rounding=ROUNDING_POLICY)


def _entries(organization, start, end, *, product=None):
    queryset = LedgerEntry.objects.for_organization(organization).filter(entry_date__range=(start, end))
    return queryset.filter(product=product) if product else queryset


def _total(queryset, category):
    return queryset.filter(account__category=category).aggregate(total=Sum("amount"))["total"] or ZERO


def gross_profit(entries):
    return money(_total(entries, AccountCategory.REVENUE) - _total(entries, AccountCategory.OPERATING_COST))


def operating_profit(entries):
    return money(gross_profit(entries) - _total(entries, AccountCategory.PAYROLL_COST))


def after_tax_result(entries):
    return money(operating_profit(entries) - _total(entries, AccountCategory.TAX))


def payroll_to_revenue_ratio(entries):
    revenue = _total(entries, AccountCategory.REVENUE)
    return ratio(_total(entries, AccountCategory.PAYROLL_COST) / revenue * 100) if revenue else ratio(ZERO)


def product_margin(entries):
    return money(gross_profit(entries) - _total(entries, AccountCategory.PAYROLL_COST))


def insurance_exposure(organization):
    """Return the total coverage limit currently carried by the organization."""
    total = (
        InsurancePolicy.objects.for_organization(organization).aggregate(total=Sum("coverage_limit"))["total"] or ZERO
    )
    return money(total)


def commission_liabilities(entries):
    """Prefer explicit commission ledger liabilities; otherwise derive them from policy premiums."""
    explicit = _total(entries, AccountCategory.COMMISSION_LIABILITY)
    if explicit:
        return money(explicit)
    liability = ZERO
    premiums = entries.filter(account__category=AccountCategory.INSURANCE_PREMIUM, policy__isnull=False).select_related(
        "policy"
    )
    for premium in premiums:
        liability += premium.amount * premium.policy.commission_rate
    return money(liability)


def calculate_metrics(organization, start, end, *, product=None, persist=False):
    entries = _entries(organization, start, end, product=product)
    premiums = _total(entries, AccountCategory.INSURANCE_PREMIUM)
    claims = _total(entries, AccountCategory.INSURANCE_CLAIM)
    values = {
        MetricType.GROSS_PROFIT: gross_profit(entries),
        MetricType.OPERATING_PROFIT: operating_profit(entries),
        MetricType.AFTER_TAX_RESULT: after_tax_result(entries),
        MetricType.PAYROLL_REVENUE_RATIO: payroll_to_revenue_ratio(entries),
        MetricType.PRODUCT_MARGIN: product_margin(entries) if product else money(ZERO),
        MetricType.INSURANCE_EXPOSURE: insurance_exposure(organization),
        MetricType.COVERAGE_MARGIN: money(premiums - claims),
        MetricType.COMMISSION_LIABILITY: commission_liabilities(entries),
    }
    if persist:
        source_ids = list(entries.values_list("id", flat=True))
        for metric_type, value in values.items():
            FinancialMetric.objects.create(
                organization=organization,
                metric_type=metric_type,
                period_start=start,
                period_end=end,
                value=value,
                product=product,
                source_entry_ids=source_ids,
            )
    return values
