"""Versioned tax rules, jurisdiction configuration, and filing records."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.organizations.models import OrganizationScopedModel


class RuleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    VALIDATED = "validated", "Validated"
    APPROVED = "approved", "Approved"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"
    REJECTED = "rejected", "Rejected"


class Jurisdiction(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160)
    country_code = models.CharField(max_length=2)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    calculator_key = models.CharField(max_length=120, blank=True)
    supported = models.BooleanField(default=False)
    filing_export_formats = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"{self.code} — {self.name}"


class TaxRuleVersion(models.Model):
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.PROTECT, related_name="rule_versions")
    version = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=RuleStatus.choices, default=RuleStatus.DRAFT, db_index=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=255, blank=True)
    source_checksum = models.CharField(max_length=64, blank=True)
    imported_payload = models.JSONField(default=dict, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_tax_rules"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("jurisdiction", "version"), name="unique_tax_rule_version"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="tax_rule_effective_dates_valid",
            ),
        ]
        indexes = [models.Index(fields=("jurisdiction", "status", "effective_from"), name="tax_rule_resolution_idx")]


class TaxYear(models.Model):
    rule_version = models.ForeignKey(TaxRuleVersion, on_delete=models.CASCADE, related_name="tax_years")
    year = models.PositiveSmallIntegerField()
    starts_on = models.DateField()
    ends_on = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("rule_version", "year"), name="unique_rule_tax_year")]


class FilingStatus(models.Model):
    rule_version = models.ForeignKey(TaxRuleVersion, on_delete=models.CASCADE, related_name="filing_statuses")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("rule_version", "code"), name="unique_rule_filing_status")]


class TaxBracket(models.Model):
    rule_version = models.ForeignKey(TaxRuleVersion, on_delete=models.CASCADE, related_name="brackets")
    filing_status = models.ForeignKey(
        FilingStatus, null=True, blank=True, on_delete=models.CASCADE, related_name="brackets"
    )
    lower_bound = models.DecimalField(max_digits=18, decimal_places=4)
    upper_bound = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    rate = models.DecimalField(max_digits=8, decimal_places=6)
    fixed_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        ordering = ("lower_bound",)
        constraints = [
            models.CheckConstraint(condition=models.Q(lower_bound__gte=0), name="tax_bracket_lower_nonnegative"),
            models.CheckConstraint(condition=models.Q(rate__gte=0), name="tax_bracket_rate_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(upper_bound__isnull=True) | models.Q(upper_bound__gt=models.F("lower_bound")),
                name="tax_bracket_bounds_valid",
            ),
        ]


class Allowance(models.Model):
    rule_version = models.ForeignKey(TaxRuleVersion, on_delete=models.CASCADE, related_name="allowances")
    code = models.CharField(max_length=60)
    amount = models.DecimalField(max_digits=18, decimal_places=4)
    filing_status = models.ForeignKey(FilingStatus, null=True, blank=True, on_delete=models.CASCADE)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("rule_version", "code"), name="unique_rule_allowance")]


class ContributionLimit(models.Model):
    rule_version = models.ForeignKey(TaxRuleVersion, on_delete=models.CASCADE, related_name="contribution_limits")
    code = models.CharField(max_length=60)
    employee_rate = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    employer_rate = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    annual_wage_base = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    annual_employee_limit = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    annual_employer_limit = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("rule_version", "code"), name="unique_rule_contribution")]


class EmployerTax(models.Model):
    rule_version = models.ForeignKey(TaxRuleVersion, on_delete=models.CASCADE, related_name="employer_taxes")
    code = models.CharField(max_length=60)
    rate = models.DecimalField(max_digits=8, decimal_places=6)
    wage_base = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    fixed_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("rule_version", "code"), name="unique_rule_employer_tax")]


class OrganizationTaxConfiguration(OrganizationScopedModel):
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.PROTECT, related_name="organization_configurations")
    required = models.BooleanField(default=True)
    external_provider_key = models.CharField(max_length=120, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "jurisdiction"), name="unique_org_tax_jurisdiction")
        ]


class FilingPeriod(OrganizationScopedModel):
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.PROTECT, related_name="filing_periods")
    period_type = models.CharField(max_length=30)
    starts_on = models.DateField()
    ends_on = models.DateField()
    due_on = models.DateField()
    status = models.CharField(max_length=20, default="open")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "jurisdiction", "period_type", "starts_on", "ends_on"),
                name="unique_tax_filing_period",
            )
        ]


class TaxLiability(OrganizationScopedModel):
    filing_period = models.ForeignKey(FilingPeriod, on_delete=models.PROTECT, related_name="liabilities")
    rule_version = models.ForeignKey(TaxRuleVersion, on_delete=models.PROTECT, related_name="liabilities")
    liability_type = models.CharField(max_length=60)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_reference = models.CharField(max_length=160, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    source_calculation_ids = models.JSONField(default=list, blank=True)


class FilingAmendment(OrganizationScopedModel):
    filing_period = models.ForeignKey(FilingPeriod, on_delete=models.PROTECT, related_name="amendments")
    sequence = models.PositiveSmallIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=20, default="draft")
    replaces_reference = models.CharField(max_length=160, blank=True)
    submitted_reference = models.CharField(max_length=160, blank=True)
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("filing_period", "sequence"), name="unique_filing_amendment")]


class FilingExport(OrganizationScopedModel):
    filing_period = models.ForeignKey(FilingPeriod, on_delete=models.PROTECT, related_name="exports")
    amendment = models.ForeignKey(
        FilingAmendment, null=True, blank=True, on_delete=models.PROTECT, related_name="exports"
    )
    format = models.CharField(max_length=40)
    payload = models.TextField()
    checksum = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.format not in self.filing_period.jurisdiction.filing_export_formats:
            raise ValidationError({"format": f"Unsupported export format for {self.filing_period.jurisdiction.code}."})
