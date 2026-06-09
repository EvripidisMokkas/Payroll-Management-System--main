"""Effective-dated compensation policy, scoring, recommendation, and approval models."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.employees.models import Employee, Salary
from apps.organizations.models import EffectiveDatedOrganizationModel, OrganizationScopedModel
from apps.organizations.validators import validate_currency, validate_identifier


class CompensationCriterion(models.TextChoices):
    SKILLS = "skills", "Skills"
    EDUCATION = "education", "Education"
    ROLE_LEVEL = "role_level", "Role level"
    EXPERIENCE = "experience", "Experience"
    PERFORMANCE = "performance", "Performance"
    TENURE = "tenure", "Tenure"
    MARKET_BENCHMARK = "market_benchmark", "Market benchmark"
    INFLATION_INDEX = "inflation_index", "Inflation index"


class RecommendationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING_APPROVAL = "pending_approval", "Pending approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    APPLIED = "applied", "Applied"


class ApprovalAction(models.TextChoices):
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    APPLIED = "applied", "Applied"


class CompensationPolicy(EffectiveDatedOrganizationModel):
    """Versioned policy envelope with compensation-change guardrails."""

    name = models.CharField(max_length=120)
    version = models.CharField(max_length=50, validators=[validate_identifier])
    currency = models.CharField(max_length=3, default="USD", validators=[validate_currency])
    is_active = models.BooleanField(default=True, db_index=True)
    minimum_adjustment_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    maximum_adjustment_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.1500"))
    budget_limit = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    budget_committed = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    require_pay_equity_review = models.BooleanField(default=True)
    pay_equity_max_deviation_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0500"))
    prohibited_criteria = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="compensation_policies"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "name", "version"), name="unique_comp_policy_version"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="comp_policy_dates_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(minimum_adjustment_percent__gte=0)
                & models.Q(maximum_adjustment_percent__gte=models.F("minimum_adjustment_percent")),
                name="comp_policy_adjustment_bounds_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(budget_limit__gte=0) & models.Q(budget_committed__gte=0),
                name="comp_policy_budget_nonnegative",
            ),
        ]
        indexes = [models.Index(fields=("organization", "name", "effective_from"), name="comp_policy_org_date_idx")]
        permissions = [
            ("approve_compensation", "Can approve compensation recommendations"),
            ("apply_compensation", "Can apply approved compensation recommendations"),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.prohibited_criteria, list) or not all(
            isinstance(item, str) and item for item in self.prohibited_criteria
        ):
            raise ValidationError({"prohibited_criteria": "Use a list of non-empty source-data field names."})
        if self.budget_committed > self.budget_limit and self.budget_limit != Decimal("0.00"):
            raise ValidationError({"budget_committed": "Committed budget cannot exceed the policy limit."})

    @property
    def budget_remaining(self):
        if self.budget_limit == Decimal("0.00"):
            return None
        return self.budget_limit - self.budget_committed

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            immutable_fields = (
                "organization_id",
                "name",
                "version",
                "currency",
                "effective_from",
                "minimum_adjustment_percent",
                "maximum_adjustment_percent",
                "budget_limit",
                "require_pay_equity_review",
                "pay_equity_max_deviation_percent",
                "prohibited_criteria",
            )
            if any(getattr(previous, field) != getattr(self, field) for field in immutable_fields):
                raise ValidationError("Published policy terms are immutable; create a new policy version instead.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Compensation policy versions must be retained for audit.")

    def __str__(self):
        return f"{self.name} {self.version}"


class ScoringRule(EffectiveDatedOrganizationModel):
    """Effective-dated weight and threshold for one scoring criterion within a policy version."""

    policy = models.ForeignKey(CompensationPolicy, on_delete=models.PROTECT, related_name="scoring_rules")
    criterion = models.CharField(max_length=32, choices=CompensationCriterion.choices)
    weight = models.DecimalField(max_digits=8, decimal_places=4)
    threshold_min = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000"))
    threshold_max = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("100.0000"))
    target_value = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("100.0000"))
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("policy", "criterion", "effective_from"), name="unique_scoring_rule_start"),
            models.CheckConstraint(condition=models.Q(weight__gte=0), name="scoring_rule_weight_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(threshold_max__gte=models.F("threshold_min")), name="scoring_rule_thresholds_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="scoring_rule_dates_valid",
            ),
        ]
        indexes = [models.Index(fields=("policy", "criterion", "effective_from"), name="scoring_rule_lookup_idx")]

    def clean(self):
        super().clean()
        if self.policy_id and self.organization_id != self.policy.organization_id:
            raise ValidationError({"policy": "Policy must belong to the same organization."})
        conflicts = ScoringRule.objects.filter(
            policy_id=self.policy_id,
            criterion=self.criterion,
            archived_at__isnull=True,
            effective_from__lte=self.effective_to or self.effective_from,
        ).exclude(pk=self.pk)
        conflicts = conflicts.filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=self.effective_from)
        )
        if conflicts.exists():
            raise ValidationError("Effective date range overlaps an existing scoring rule for this criterion.")

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            immutable_fields = (
                "organization_id",
                "policy_id",
                "criterion",
                "weight",
                "threshold_min",
                "threshold_max",
                "target_value",
                "effective_from",
                "metadata",
            )
            if any(getattr(previous, field) != getattr(self, field) for field in immutable_fields):
                raise ValidationError(
                    "Published scoring rules are immutable; create a new effective-dated rule instead."
                )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Scoring rules must be retained for audit.")


class CompensationRecommendation(OrganizationScopedModel):
    """Immutable recommendation result retained for audit before any salary is changed."""

    policy = models.ForeignKey(CompensationPolicy, on_delete=models.PROTECT, related_name="recommendations")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="compensation_recommendations")
    current_salary = models.ForeignKey(
        Salary, null=True, blank=True, on_delete=models.PROTECT, related_name="compensation_recommendations"
    )
    resulting_salary = models.OneToOneField(
        Salary, null=True, blank=True, on_delete=models.PROTECT, related_name="source_recommendation"
    )
    as_of_date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=RecommendationStatus.choices,
        default=RecommendationStatus.PENDING_APPROVAL,
        db_index=True,
    )
    score = models.DecimalField(max_digits=8, decimal_places=4)
    score_breakdown = models.JSONField()
    source_data_snapshot = models.JSONField()
    policy_snapshot = models.JSONField()
    proposed_min = models.DecimalField(max_digits=16, decimal_places=2)
    proposed_midpoint = models.DecimalField(max_digits=16, decimal_places=2)
    proposed_max = models.DecimalField(max_digits=16, decimal_places=2)
    proposed_adjustment = models.DecimalField(max_digits=16, decimal_places=2)
    currency = models.CharField(max_length=3, validators=[validate_currency])
    explanation = models.TextField()
    controls = models.JSONField(default=dict)
    pay_equity_reviewed = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="created_comp_recs"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=("employee", "as_of_date", "created_at"), name="comp_rec_employee_date_idx"),
            models.Index(fields=("policy", "status"), name="comp_rec_policy_status_idx"),
        ]

    def clean(self):
        super().clean()
        if self.employee_id and self.organization_id != self.employee.organization_id:
            raise ValidationError({"employee": "Employee must belong to the same organization."})
        if self.policy_id and self.organization_id != self.policy.organization_id:
            raise ValidationError({"policy": "Policy must belong to the same organization."})
        if self.current_salary_id and self.organization_id != self.current_salary.organization_id:
            raise ValidationError({"current_salary": "Salary must belong to the same organization."})
        if self.resulting_salary_id and self.organization_id != self.resulting_salary.organization_id:
            raise ValidationError({"resulting_salary": "Salary must belong to the same organization."})

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            immutable_fields = (
                "policy_id",
                "employee_id",
                "current_salary_id",
                "as_of_date",
                "score",
                "score_breakdown",
                "source_data_snapshot",
                "policy_snapshot",
                "proposed_min",
                "proposed_midpoint",
                "proposed_max",
                "proposed_adjustment",
                "currency",
                "explanation",
                "controls",
            )
            if any(getattr(previous, field) != getattr(self, field) for field in immutable_fields):
                raise ValidationError(
                    "Recommendation scoring results are immutable; create a new recommendation instead."
                )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Compensation recommendations must be retained for audit.")


class CompensationApproval(OrganizationScopedModel):
    """Append-only human approval/rejection/application event for a recommendation."""

    recommendation = models.ForeignKey(CompensationRecommendation, on_delete=models.PROTECT, related_name="approvals")
    action = models.CharField(max_length=20, choices=ApprovalAction.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compensation_approvals")
    actor_role = models.CharField(max_length=32)
    explanation = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=("recommendation", "created_at"), name="comp_approval_rec_created_idx")]

    def clean(self):
        super().clean()
        if self.recommendation_id and self.organization_id != self.recommendation.organization_id:
            raise ValidationError({"recommendation": "Recommendation must belong to the same organization."})

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Compensation approval events are append-only.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Compensation approval events are append-only.")
