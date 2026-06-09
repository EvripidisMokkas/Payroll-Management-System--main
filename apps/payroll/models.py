"""Auditable organization-scoped payroll domain records.

Calculations and lifecycle transitions intentionally live in service modules. Models
store inputs, immutable snapshots, and results; they do not contain payroll rules.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.organizations.models import OrganizationScopedModel
from apps.organizations.validators import validate_currency


class PayrollLifecycle(models.TextChoices):
    DRAFT = "draft", "Draft"
    VALIDATION = "validation", "Validation"
    APPROVAL = "approval", "Approval"
    LOCKED = "locked", "Locked"
    PAID = "paid", "Paid"
    CORRECTED = "corrected", "Corrected"
    ARCHIVED = "archived", "Archived"


PROTECTED_PERIOD_STATUSES = {
    PayrollLifecycle.LOCKED,
    PayrollLifecycle.PAID,
    PayrollLifecycle.CORRECTED,
    PayrollLifecycle.ARCHIVED,
}


class InputType(models.TextChoices):
    BASE_SALARY = "base_salary", "Base salary"
    HOURLY = "hourly", "Hourly work"
    OVERTIME = "overtime", "Overtime"
    BONUS = "bonus", "Bonus"
    COMMISSION = "commission", "Commission"
    BENEFIT = "benefit", "Benefit"
    PRE_TAX_DEDUCTION = "pre_tax_deduction", "Pre-tax deduction"
    POST_TAX_DEDUCTION = "post_tax_deduction", "Post-tax deduction"
    EMPLOYER_COST = "employer_cost", "Employer cost"


class LineItemCategory(models.TextChoices):
    EARNING = "earning", "Earning"
    BENEFIT = "benefit", "Benefit"
    PRE_TAX_DEDUCTION = "pre_tax_deduction", "Pre-tax deduction"
    POST_TAX_DEDUCTION = "post_tax_deduction", "Post-tax deduction"
    EMPLOYER_COST = "employer_cost", "Employer cost"


class ImmutableSnapshotModel(models.Model):
    """Reject updates and deletes so recorded payroll evidence remains reproducible."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Immutable payroll snapshots cannot be modified.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Immutable payroll snapshots cannot be deleted.")


class PaySchedule(OrganizationScopedModel):
    name = models.CharField(max_length=120)
    frequency = models.CharField(
        max_length=20,
        choices=[
            ("weekly", "Weekly"),
            ("biweekly", "Biweekly"),
            ("semimonthly", "Semimonthly"),
            ("monthly", "Monthly"),
        ],
    )
    periods_per_year = models.PositiveSmallIntegerField()
    currency = models.CharField(max_length=3, default="USD", validators=[validate_currency])
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "name"), name="unique_pay_schedule_name")]


class PayrollPeriod(OrganizationScopedModel):
    schedule = models.ForeignKey(PaySchedule, on_delete=models.PROTECT, related_name="periods")
    period_start = models.DateField()
    period_end = models.DateField()
    pay_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=PayrollLifecycle.choices, default=PayrollLifecycle.DRAFT, db_index=True
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("schedule", "period_start", "period_end"), name="unique_payroll_period"),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")), name="payroll_period_dates_valid"
            ),
        ]
        permissions = [
            ("operate_payroll", "Can create and validate payroll operations"),
            ("approve_payroll", "Can approve and lock payroll"),
            ("mark_payroll_paid", "Can mark payroll paid"),
        ]

    def clean(self):
        super().clean()
        if self.schedule_id and self.organization_id != self.schedule.organization_id:
            raise ValidationError({"schedule": "Schedule must belong to the payroll period organization."})
        if self.period_end < self.period_start:
            raise ValidationError({"period_end": "Period end cannot precede period start."})
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and previous.status != self.status:
                raise ValidationError({"status": "Use the payroll lifecycle service for status transitions."})
            protected_fields = ("organization_id", "schedule_id", "period_start", "period_end", "pay_date")
            if (
                previous
                and previous.status in PROTECTED_PERIOD_STATUSES
                and any(getattr(previous, field) != getattr(self, field) for field in protected_fields)
            ):
                raise ValidationError("Locked and paid payroll periods cannot be modified.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class EmployeePayrollInput(OrganizationScopedModel):
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="employee_inputs")
    employee = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name="payroll_inputs")
    input_type = models.CharField(max_length=30, choices=InputType.choices)
    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    quantity = models.DecimalField(max_digits=12, decimal_places=4, default=1)
    rate = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    source_key = models.CharField(max_length=120)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("period", "employee", "source_key"), name="unique_payroll_input_source"),
        ]
        indexes = [models.Index(fields=("period", "employee"), name="pay_input_period_employee_idx")]

    def clean(self):
        super().clean()
        if self.period_id and self.organization_id != self.period.organization_id:
            raise ValidationError({"period": "Period must belong to the input organization."})
        if self.employee_id and self.organization_id != self.employee.organization_id:
            raise ValidationError({"employee": "Employee must belong to the input organization."})
        if self.amount < 0 or self.quantity < 0 or self.rate < 0:
            raise ValidationError("Regular payroll inputs cannot be negative; use an adjustment run for corrections.")
        if self.period_id and self.period.status in PROTECTED_PERIOD_STATUSES:
            raise ValidationError("Inputs for locked or paid payroll periods cannot be modified.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.period.status in PROTECTED_PERIOD_STATUSES:
            raise ValidationError("Inputs for locked or paid payroll periods cannot be deleted.")
        return super().delete(*args, **kwargs)


class CalculationRun(ImmutableSnapshotModel, OrganizationScopedModel):
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="calculation_runs")
    adjustment_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="adjustments"
    )
    rules_version = models.CharField(max_length=50)
    tax_jurisdiction_code = models.CharField(max_length=32, default="not_applicable")
    tax_rule_version = models.CharField(max_length=80, default="not_applicable")
    idempotency_key = models.CharField(max_length=160)
    input_snapshot = models.JSONField()
    rules_snapshot = models.JSONField()
    explanation = models.JSONField(default=dict)
    gross_pay = models.DecimalField(max_digits=16, decimal_places=2)
    pre_tax_deductions = models.DecimalField(max_digits=16, decimal_places=2)
    post_tax_deductions = models.DecimalField(max_digits=16, decimal_places=2)
    employer_costs = models.DecimalField(max_digits=16, decimal_places=2)
    net_pay = models.DecimalField(max_digits=16, decimal_places=2)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="payroll_runs"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "idempotency_key"), name="unique_payroll_run_idempotency")
        ]
        indexes = [models.Index(fields=("period", "created_at"), name="pay_run_period_created_idx")]


class PayrollLineItem(ImmutableSnapshotModel, OrganizationScopedModel):
    run = models.ForeignKey(CalculationRun, on_delete=models.PROTECT, related_name="line_items")
    employee = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name="payroll_line_items")
    input_type = models.CharField(max_length=30, choices=InputType.choices)
    category = models.CharField(max_length=30, choices=LineItemCategory.choices)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    explanation = models.JSONField(default=dict)
    source_snapshot = models.JSONField(default=dict)


class PayrollApproval(ImmutableSnapshotModel, OrganizationScopedModel):
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="approvals")
    from_status = models.CharField(max_length=20, choices=PayrollLifecycle.choices)
    to_status = models.CharField(max_length=20, choices=PayrollLifecycle.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payroll_approvals")
    actor_role = models.CharField(max_length=32)
    explanation = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class PayrollCorrection(ImmutableSnapshotModel, OrganizationScopedModel):
    original_period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="corrections")
    adjustment_run = models.OneToOneField(CalculationRun, on_delete=models.PROTECT, related_name="correction")
    reason = models.TextField()
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payroll_corrections"
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Payslip(ImmutableSnapshotModel, OrganizationScopedModel):
    run = models.ForeignKey(CalculationRun, on_delete=models.PROTECT, related_name="payslips")
    employee = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name="payslips")
    gross_pay = models.DecimalField(max_digits=16, decimal_places=2)
    net_pay = models.DecimalField(max_digits=16, decimal_places=2)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("run", "employee"), name="unique_run_employee_payslip")]


class PaymentBatch(ImmutableSnapshotModel, OrganizationScopedModel):
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="payment_batches")
    run = models.ForeignKey(CalculationRun, on_delete=models.PROTECT, related_name="payment_batches")
    idempotency_key = models.CharField(max_length=160)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2)
    payment_count = models.PositiveIntegerField()
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "idempotency_key"), name="unique_payment_batch_idempotency")
        ]


class PayrollRecord(OrganizationScopedModel):
    """Legacy summary record retained for API compatibility."""

    employee = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="payroll_records"
    )
    employee_name = models.CharField(max_length=200)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, default="draft")

    class Meta:
        permissions = [("operate_legacy_payroll", "Can create and update legacy payroll operations")]
