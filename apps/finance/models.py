"""Normalized financial ledger, metrics, insurance, and forecasting records."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.organizations.models import OrganizationScopedModel
from apps.organizations.validators import validate_currency


class AccountCategory(models.TextChoices):
    REVENUE = "revenue", "Revenue"
    OPERATING_COST = "operating_cost", "Operating cost"
    PAYROLL_COST = "payroll_cost", "Payroll cost"
    TAX = "tax", "Tax"
    INVESTMENT_FUND = "investment_fund", "Investment fund"
    INSURANCE_PREMIUM = "insurance_premium", "Insurance premium"
    INSURANCE_CLAIM = "insurance_claim", "Insurance claim"
    COMMISSION_LIABILITY = "commission_liability", "Commission liability"


class FinancialAccount(OrganizationScopedModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=32, choices=AccountCategory.choices, db_index=True)
    currency = models.CharField(max_length=3, default="USD", validators=[validate_currency])
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "code"), name="unique_finance_account_code")]
        indexes = [models.Index(fields=("organization", "category"), name="fin_account_org_cat_idx")]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Product(OrganizationScopedModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "code"), name="unique_finance_product_code")]


class InvestmentFund(OrganizationScopedModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    target_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "code"), name="unique_investment_fund_code")]


class InsurancePolicy(OrganizationScopedModel):
    policy_number = models.CharField(max_length=80)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="insurance_policies")
    coverage_limit = models.DecimalField(max_digits=18, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0"))
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "policy_number"), name="unique_policy_number")]

    def clean(self):
        super().clean()
        if self.product_id and self.product.organization_id != self.organization_id:
            raise ValidationError({"product": "Product must belong to the same organization."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Policy end date cannot precede its start date."})


class ClaimStatus(models.TextChoices):
    REPORTED = "reported", "Reported"
    RESERVED = "reserved", "Reserved"
    PAID = "paid", "Paid"
    DENIED = "denied", "Denied"
    CLOSED = "closed", "Closed"


class InsuranceClaim(OrganizationScopedModel):
    policy = models.ForeignKey(InsurancePolicy, on_delete=models.PROTECT, related_name="claims")
    claim_number = models.CharField(max_length=80)
    occurred_on = models.DateField()
    reported_on = models.DateField()
    claimed_amount = models.DecimalField(max_digits=18, decimal_places=2)
    reserved_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=20, choices=ClaimStatus.choices, default=ClaimStatus.REPORTED)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "claim_number"), name="unique_claim_number")]

    def clean(self):
        super().clean()
        if self.policy_id and self.policy.organization_id != self.organization_id:
            raise ValidationError({"policy": "Policy must belong to the same organization."})
        if self.reported_on < self.occurred_on:
            raise ValidationError({"reported_on": "Report date cannot precede occurrence date."})


class LedgerEntry(OrganizationScopedModel):
    account = models.ForeignKey(FinancialAccount, on_delete=models.PROTECT, related_name="entries")
    entry_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    description = models.CharField(max_length=255)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries")
    investment_fund = models.ForeignKey(
        InvestmentFund, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries"
    )
    policy = models.ForeignKey(
        InsurancePolicy, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries"
    )
    source_type = models.CharField(max_length=80, help_text="Name of the source system or record type.")
    source_reference = models.CharField(max_length=160, help_text="Stable reference to the underlying source record.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("organization", "entry_date"), name="ledger_org_date_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "source_type", "source_reference", "account"),
                name="unique_ledger_source_account",
            )
        ]

    def clean(self):
        super().clean()
        for field in ("account", "product", "investment_fund", "policy"):
            value = getattr(self, field, None)
            if value and value.organization_id != self.organization_id:
                raise ValidationError(
                    {field: f"{field.replace('_', ' ').title()} must belong to the same organization."}
                )


class MetricType(models.TextChoices):
    GROSS_PROFIT = "gross_profit", "Gross profit"
    OPERATING_PROFIT = "operating_profit", "Operating profit"
    AFTER_TAX_RESULT = "after_tax_result", "After-tax result"
    PAYROLL_REVENUE_RATIO = "payroll_revenue_ratio", "Payroll-to-revenue ratio"
    PRODUCT_MARGIN = "product_margin", "Product margin"
    INSURANCE_EXPOSURE = "insurance_exposure", "Insurance exposure"
    COVERAGE_MARGIN = "coverage_margin", "Coverage margin"
    COMMISSION_LIABILITY = "commission_liability", "Commission liability"


class FinancialMetric(OrganizationScopedModel):
    metric_type = models.CharField(max_length=40, choices=MetricType.choices)
    period_start = models.DateField()
    period_end = models.DateField()
    value = models.DecimalField(max_digits=20, decimal_places=4)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT, related_name="metrics")
    source_entry_ids = models.JSONField(default=list)
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("organization", "metric_type", "period_end"), name="metric_org_type_end_idx")]

    def clean(self):
        super().clean()
        if self.product_id and self.product.organization_id != self.organization_id:
            raise ValidationError({"product": "Product must belong to the same organization."})


class DataQualityWarning(OrganizationScopedModel):
    code = models.CharField(max_length=60)
    message = models.TextField()
    source_type = models.CharField(max_length=80, blank=True)
    source_reference = models.CharField(max_length=160, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


class ForecastRun(OrganizationScopedModel):
    """Auditable prediction metadata. Forecasts are never guaranteed outcomes."""

    metric_type = models.CharField(max_length=40, choices=MetricType.choices)
    model_version = models.CharField(max_length=80)
    assumptions = models.JSONField(default=dict)
    source_data_start = models.DateField()
    source_data_end = models.DateField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    disclaimer = models.TextField(
        default="Prediction only — confidence ranges express uncertainty and outcomes are not guaranteed."
    )


class ForecastPoint(OrganizationScopedModel):
    run = models.ForeignKey(ForecastRun, on_delete=models.PROTECT, related_name="points")
    forecast_date = models.DateField()
    predicted_value = models.DecimalField(max_digits=20, decimal_places=4)
    confidence_low = models.DecimalField(max_digits=20, decimal_places=4)
    confidence_high = models.DecimalField(max_digits=20, decimal_places=4)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("run", "forecast_date"), name="unique_forecast_run_date")]

    def clean(self):
        super().clean()
        if self.run_id and self.run.organization_id != self.organization_id:
            raise ValidationError({"run": "Forecast run must belong to the same organization."})
