"""Employee profiles, employment records, sensitive data, and payroll terms."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.organizations.models import (
    ArchivableOrganizationModel,
    EffectiveDatedOrganizationModel,
    OrganizationScopedModel,
)
from apps.organizations.validators import validate_currency, validate_identifier
from apps.security.fields import EncryptedTextField


class EmploymentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    LEAVE = "leave", "On leave"
    TERMINATED = "terminated", "Terminated"
    ARCHIVED = "archived", "Archived"


ALLOWED_STATUS_TRANSITIONS = {
    EmploymentStatus.DRAFT: {EmploymentStatus.ACTIVE, EmploymentStatus.ARCHIVED},
    EmploymentStatus.ACTIVE: {EmploymentStatus.LEAVE, EmploymentStatus.TERMINATED},
    EmploymentStatus.LEAVE: {EmploymentStatus.ACTIVE, EmploymentStatus.TERMINATED},
    EmploymentStatus.TERMINATED: {EmploymentStatus.ARCHIVED},
    EmploymentStatus.ARCHIVED: set(),
}


class Employee(ArchivableOrganizationModel):
    """General, broadly visible employee profile. Sensitive values live elsewhere."""

    employee_number = models.CharField(max_length=50, validators=[validate_identifier])
    preferred_name = models.CharField(max_length=100, blank=True)
    given_name = models.CharField(max_length=100)
    family_name = models.CharField(max_length=100)
    work_email = models.EmailField(blank=True)
    work_phone = models.CharField(max_length=50, blank=True)
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=EmploymentStatus.choices, default=EmploymentStatus.DRAFT, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "employee_number"), name="unique_employee_number_per_org"),
            models.CheckConstraint(
                condition=models.Q(termination_date__isnull=True)
                | models.Q(termination_date__gte=models.F("hire_date")),
                name="employee_dates_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("organization", "status"), name="employee_org_status_idx"),
            models.Index(fields=("organization", "family_name", "given_name"), name="employee_org_name_idx"),
        ]
        permissions = [("view_employee_sensitive", "Can view employee sensitive-data records")]

    def clean(self):
        super().clean()
        if self.termination_date and self.termination_date < self.hire_date:
            raise ValidationError({"termination_date": "Termination date cannot precede hire date."})
        if self.status == EmploymentStatus.TERMINATED and not self.termination_date:
            raise ValidationError({"termination_date": "Terminated employees require a termination date."})
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous and previous != self.status and self.status not in ALLOWED_STATUS_TRANSITIONS[previous]:
                raise ValidationError(
                    {"status": f"Cannot transition employment status from {previous} to {self.status}."}
                )

    def __str__(self):
        return f"{self.employee_number} — {self.given_name} {self.family_name}"


class EmployeePersonalInformation(ArchivableOrganizationModel):
    """Restricted personal data; encrypted/tokenized values must be decrypted by an application service."""

    employee = models.OneToOneField(Employee, on_delete=models.PROTECT, related_name="personal_information")
    legal_name_encrypted = EncryptedTextField(blank=True)
    date_of_birth_encrypted = EncryptedTextField(blank=True)
    personal_email_encrypted = EncryptedTextField(blank=True)
    personal_phone_encrypted = EncryptedTextField(blank=True)
    residential_address_encrypted = EncryptedTextField(blank=True)
    government_id_token = models.CharField(max_length=255, blank=True)
    emergency_contact_encrypted = EncryptedTextField(blank=True)

    class Meta:
        permissions = [
            ("view_personal_information", "Can view restricted employee personal information"),
            ("change_personal_information", "Can change restricted employee personal information"),
        ]

    def clean(self):
        super().clean()
        self._validate_employee_organization()

    def _validate_employee_organization(self):
        if self.employee_id and self.organization_id != self.employee.organization_id:
            raise ValidationError({"employee": "Employee must belong to the same organization."})


class EmployeeBankAccount(ArchivableOrganizationModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="bank_accounts")
    account_holder_encrypted = EncryptedTextField()
    account_number_token = models.CharField(max_length=255)
    account_fingerprint = models.CharField(max_length=128, help_text="Keyed hash used only for duplicate detection.")
    routing_details_encrypted = EncryptedTextField()
    currency = models.CharField(max_length=3, validators=[validate_currency])
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "account_fingerprint"), name="unique_bank_fingerprint_per_org"
            ),
            models.UniqueConstraint(
                fields=("employee",),
                condition=models.Q(is_primary=True, archived_at__isnull=True),
                name="one_primary_bank_per_employee",
            ),
        ]
        permissions = [
            ("view_banking_information", "Can view restricted employee banking information"),
            ("change_banking_information", "Can change restricted employee banking information"),
        ]

    def clean(self):
        super().clean()
        if self.employee_id and self.organization_id != self.employee.organization_id:
            raise ValidationError({"employee": "Employee must belong to the same organization."})


class EmployeeTaxProfile(EffectiveDatedOrganizationModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="tax_profiles")
    jurisdiction = models.CharField(max_length=20)
    tax_identifier_token = models.CharField(max_length=255)
    tax_identifier_fingerprint = models.CharField(max_length=128)
    elections_encrypted = EncryptedTextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "tax_identifier_fingerprint"), name="unique_tax_fingerprint_per_org"
            ),
            models.UniqueConstraint(
                fields=("employee", "jurisdiction", "effective_from"), name="unique_tax_period_start"
            ),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="tax_profile_dates_valid",
            ),
        ]
        permissions = [
            ("view_tax_information", "Can view restricted employee tax information"),
            ("change_tax_information", "Can change restricted employee tax information"),
        ]

    def clean(self):
        super().clean()
        validate_employee_period(self)


class Department(ArchivableOrganizationModel):
    code = models.CharField(max_length=50, validators=[validate_identifier])
    name = models.CharField(max_length=200)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "code"), name="unique_department_code_per_org")]

    def __str__(self):
        return self.name


class Position(ArchivableOrganizationModel):
    code = models.CharField(max_length=50, validators=[validate_identifier])
    title = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="positions")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "code"), name="unique_position_code_per_org")]

    def clean(self):
        super().clean()
        if self.department_id and self.organization_id != self.department.organization_id:
            raise ValidationError({"department": "Department must belong to the same organization."})

    def __str__(self):
        return self.title


def validate_employee_period(instance):
    """Validate tenant ownership and prevent overlapping effective periods for a record type."""
    if not instance.employee_id:
        return
    if instance.organization_id != instance.employee.organization_id:
        raise ValidationError({"employee": "Employee must belong to the same organization."})
    conflicts = (
        type(instance)
        .objects.filter(employee_id=instance.employee_id, archived_at__isnull=True)
        .exclude(pk=instance.pk)
    )
    if hasattr(instance, "kind"):
        conflicts = conflicts.filter(kind=instance.kind)
    if hasattr(instance, "jurisdiction"):
        conflicts = conflicts.filter(jurisdiction=instance.jurisdiction)
    if hasattr(instance, "product_id") and instance.product_id:
        if instance.organization_id != instance.product.organization_id:
            raise ValidationError({"product": "Product must belong to the same organization."})
        conflicts = conflicts.filter(product_id=instance.product_id)
    conflicts = conflicts.filter(
        models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=instance.effective_from)
    )
    if instance.effective_to:
        conflicts = conflicts.filter(effective_from__lte=instance.effective_to)
    if conflicts.exists():
        raise ValidationError("Effective date range overlaps an existing active record.")


class EmployeeEffectiveDatedModel(EffectiveDatedOrganizationModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        validate_employee_period(self)


class EmploymentHistory(EmployeeEffectiveDatedModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="employment_history")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="employee_history")
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name="employee_history")
    manager = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.PROTECT, related_name="managed_history"
    )
    status = models.CharField(max_length=20, choices=EmploymentStatus.choices)
    location = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("employee", "effective_from"), name="unique_employment_history_start"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="employment_history_dates_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("employee", "effective_from", "effective_to"), name="employment_history_period_idx")
        ]

    def clean(self):
        super().clean()
        for field in ("department", "position", "manager"):
            value = getattr(self, field, None)
            if value and value.organization_id != self.organization_id:
                raise ValidationError({field: f"{field.title()} must belong to the same organization."})
        if self.position_id and self.department_id and self.position.department_id != self.department_id:
            raise ValidationError({"position": "Position must belong to the selected department."})


def validate_employee_ownership(instance):
    if instance.employee_id and instance.organization_id != instance.employee.organization_id:
        raise ValidationError({"employee": "Employee must belong to the same organization."})


class Qualification(ArchivableOrganizationModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="qualifications")
    name = models.CharField(max_length=200)
    issuing_body = models.CharField(max_length=200, blank=True)
    awarded_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    credential_reference = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("employee", "name", "issuing_body"), name="unique_employee_qualification"),
            models.CheckConstraint(
                condition=models.Q(expires_on__isnull=True)
                | models.Q(awarded_on__isnull=True)
                | models.Q(expires_on__gte=models.F("awarded_on")),
                name="qualification_dates_valid",
            ),
        ]

    def clean(self):
        super().clean()
        validate_employee_ownership(self)
        if self.awarded_on and self.expires_on and self.expires_on < self.awarded_on:
            raise ValidationError({"expires_on": "Expiry date cannot precede award date."})


class Skill(ArchivableOrganizationModel):
    name = models.CharField(max_length=100)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "name"), name="unique_skill_name_per_org")]


class EmployeeSkill(ArchivableOrganizationModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="skills")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="employees")
    proficiency = models.CharField(
        max_length=20,
        choices=[("basic", "Basic"), ("intermediate", "Intermediate"), ("advanced", "Advanced"), ("expert", "Expert")],
    )
    years_experience = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("employee", "skill"), name="unique_employee_skill"),
            models.CheckConstraint(condition=models.Q(years_experience__gte=0), name="skill_experience_nonnegative"),
        ]

    def clean(self):
        super().clean()
        validate_employee_ownership(self)
        if self.skill_id and self.organization_id != self.skill.organization_id:
            raise ValidationError({"skill": "Skill must belong to the same organization."})


class Experience(ArchivableOrganizationModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="experience")
    employer = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    started_on = models.DateField()
    ended_on = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ended_on__isnull=True) | models.Q(ended_on__gte=models.F("started_on")),
                name="experience_dates_valid",
            )
        ]

    def clean(self):
        super().clean()
        validate_employee_ownership(self)
        if self.ended_on and self.ended_on < self.started_on:
            raise ValidationError({"ended_on": "End date cannot precede start date."})


class EmploymentContract(EmployeeEffectiveDatedModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="contracts")
    contract_number = models.CharField(max_length=100, validators=[validate_identifier])
    employment_type = models.CharField(
        max_length=30,
        choices=[
            ("permanent", "Permanent"),
            ("fixed_term", "Fixed term"),
            ("casual", "Casual"),
            ("contractor", "Contractor"),
        ],
    )
    hours_per_week = models.DecimalField(max_digits=5, decimal_places=2)
    notice_days = models.PositiveSmallIntegerField(default=0)
    terms_document_reference = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "contract_number"), name="unique_contract_number_per_org"),
            models.CheckConstraint(condition=models.Q(hours_per_week__gt=0), name="contract_hours_positive"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="contract_dates_valid",
            ),
        ]


class Salary(EmployeeEffectiveDatedModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="salaries")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, validators=[validate_currency])
    frequency = models.CharField(
        max_length=20,
        choices=[("hourly", "Hourly"), ("weekly", "Weekly"), ("monthly", "Monthly"), ("annual", "Annual")],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("employee", "effective_from"), name="unique_salary_period_start"),
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="salary_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="salary_dates_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("employee", "effective_from", "effective_to"), name="salary_employee_period_idx")
        ]


class BenefitPlan(ArchivableOrganizationModel):
    code = models.CharField(max_length=50, validators=[validate_identifier])
    name = models.CharField(max_length=200)
    provider = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "code"), name="unique_benefit_code_per_org")]


class BenefitEnrollment(EmployeeEffectiveDatedModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="benefit_enrollments")
    product = models.ForeignKey(BenefitPlan, on_delete=models.PROTECT, related_name="enrollments")
    employee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    employer_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, validators=[validate_currency])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("employee", "product", "effective_from"), name="unique_benefit_period_start"
            ),
            models.CheckConstraint(
                condition=models.Q(employee_amount__gte=0, employer_amount__gte=0), name="benefit_amounts_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="benefit_dates_valid",
            ),
        ]


class Deduction(EmployeeEffectiveDatedModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="deductions")
    kind = models.CharField(max_length=50, validators=[validate_identifier])
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, validators=[validate_currency])
    reference = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("employee", "kind", "effective_from"), name="unique_deduction_period_start"
            ),
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="deduction_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="deduction_dates_valid",
            ),
        ]


class CommissionPlan(EmployeeEffectiveDatedModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="commission_plans")
    kind = models.CharField(max_length=50, default="standard", validators=[validate_identifier])
    rate = models.DecimalField(max_digits=7, decimal_places=4)
    threshold_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, validators=[validate_currency])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("employee", "kind", "effective_from"), name="unique_commission_period_start"
            ),
            models.CheckConstraint(
                condition=models.Q(rate__gte=0) & models.Q(rate__lte=Decimal("1")), name="commission_rate_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(threshold_amount__gte=0), name="commission_threshold_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="commission_dates_valid",
            ),
        ]


class InsuranceCoverage(EmployeeEffectiveDatedModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="insurance_coverages")
    kind = models.CharField(max_length=50, validators=[validate_identifier])
    provider = models.CharField(max_length=200)
    policy_token = models.CharField(
        max_length=255, help_text="Tokenized policy identifier; do not store plaintext policy numbers."
    )
    coverage_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, validators=[validate_currency])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("employee", "kind", "effective_from"), name="unique_insurance_period_start"
            ),
            models.CheckConstraint(condition=models.Q(coverage_amount__gte=0), name="insurance_coverage_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="insurance_dates_valid",
            ),
        ]


class PayrollProduct(ArchivableOrganizationModel):
    code = models.CharField(max_length=50, validators=[validate_identifier])
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=50, validators=[validate_identifier])

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "code"), name="unique_payroll_product_code")]


class EmployeeProductAssignment(EmployeeEffectiveDatedModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="product_assignments")
    product = models.ForeignKey(PayrollProduct, on_delete=models.PROTECT, related_name="employee_assignments")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("employee", "product", "effective_from"), name="unique_product_period_start"
            ),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="product_assignment_dates_valid",
            ),
        ]
        indexes = [models.Index(fields=("employee", "product", "effective_from"), name="product_assignment_period_idx")]


class PrivacyRequestType(models.TextChoices):
    EXPORT = "export", "Export"
    CORRECTION = "correction", "Correction"
    DELETION = "deletion", "Deletion"
    RETENTION_REVIEW = "retention_review", "Retention review"


class PrivacyRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending verification"
    APPROVED = "approved", "Approved"
    COMPLETED = "completed", "Completed"
    REJECTED = "rejected", "Rejected"


class DataSubjectRequest(OrganizationScopedModel):
    """Auditable workflow record for a verified employee privacy request."""

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="privacy_requests")
    request_type = models.CharField(max_length=24, choices=PrivacyRequestType.choices)
    status = models.CharField(max_length=20, choices=PrivacyRequestStatus.choices, default=PrivacyRequestStatus.PENDING)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="requested_privacy_requests"
    )
    approved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="approved_privacy_requests"
    )
    reason = models.TextField(blank=True)
    legal_basis = models.TextField(blank=True)
    response_sha256 = models.CharField(max_length=64, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [("manage_privacy_requests", "Can review and execute employee privacy requests")]

    def clean(self):
        super().clean()
        if self.employee_id and self.organization_id != self.employee.organization_id:
            raise ValidationError({"employee": "Employee must belong to the same organization."})
