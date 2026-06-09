# Generated for the effective-dated compensation recommendation domain.

import decimal
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import apps.organizations.validators


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("employees", "0001_initial"),
        ("organizations", "0002_organization_legal_billing_lifecycle"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CompensationPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("retention_until", models.DateField(blank=True, db_index=True, null=True)),
                ("effective_from", models.DateField(db_index=True)),
                ("effective_to", models.DateField(blank=True, db_index=True, null=True)),
                ("name", models.CharField(max_length=120)),
                ("version", models.CharField(max_length=50, validators=[apps.organizations.validators.validate_identifier])),
                ("currency", models.CharField(default="USD", max_length=3, validators=[apps.organizations.validators.validate_currency])),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("minimum_adjustment_percent", models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0000"), max_digits=7)),
                ("maximum_adjustment_percent", models.DecimalField(decimal_places=4, default=decimal.Decimal("0.1500"), max_digits=7)),
                ("budget_limit", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=16)),
                ("budget_committed", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=16)),
                ("require_pay_equity_review", models.BooleanField(default=True)),
                ("pay_equity_max_deviation_percent", models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0500"), max_digits=7)),
                ("prohibited_criteria", models.JSONField(blank=True, default=list)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="compensation_policies", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
            ],
            options={
                "permissions": [("approve_compensation", "Can approve compensation recommendations"), ("apply_compensation", "Can apply approved compensation recommendations")],
                "indexes": [models.Index(fields=["organization", "name", "effective_from"], name="comp_policy_org_date_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("organization", "name", "version"), name="unique_comp_policy_version"),
                    models.CheckConstraint(condition=models.Q(("effective_to__isnull", True), ("effective_to__gte", models.F("effective_from")), _connector="OR"), name="comp_policy_dates_valid"),
                    models.CheckConstraint(condition=models.Q(("minimum_adjustment_percent__gte", 0), ("maximum_adjustment_percent__gte", models.F("minimum_adjustment_percent"))), name="comp_policy_adjustment_bounds_valid"),
                    models.CheckConstraint(condition=models.Q(("budget_limit__gte", 0), ("budget_committed__gte", 0)), name="comp_policy_budget_nonnegative"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ScoringRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("retention_until", models.DateField(blank=True, db_index=True, null=True)),
                ("effective_from", models.DateField(db_index=True)),
                ("effective_to", models.DateField(blank=True, db_index=True, null=True)),
                ("criterion", models.CharField(choices=[("skills", "Skills"), ("education", "Education"), ("role_level", "Role level"), ("experience", "Experience"), ("performance", "Performance"), ("tenure", "Tenure"), ("market_benchmark", "Market benchmark"), ("inflation_index", "Inflation index")], max_length=32)),
                ("weight", models.DecimalField(decimal_places=4, max_digits=8)),
                ("threshold_min", models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0000"), max_digits=12)),
                ("threshold_max", models.DecimalField(decimal_places=4, default=decimal.Decimal("100.0000"), max_digits=12)),
                ("target_value", models.DecimalField(decimal_places=4, default=decimal.Decimal("100.0000"), max_digits=12)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="scoring_rules", to="compensation.compensationpolicy")),
            ],
            options={
                "indexes": [models.Index(fields=["policy", "criterion", "effective_from"], name="scoring_rule_lookup_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("policy", "criterion", "effective_from"), name="unique_scoring_rule_start"),
                    models.CheckConstraint(condition=models.Q(("weight__gte", 0)), name="scoring_rule_weight_nonnegative"),
                    models.CheckConstraint(condition=models.Q(("threshold_max__gte", models.F("threshold_min"))), name="scoring_rule_thresholds_valid"),
                    models.CheckConstraint(condition=models.Q(("effective_to__isnull", True), ("effective_to__gte", models.F("effective_from")), _connector="OR"), name="scoring_rule_dates_valid"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CompensationRecommendation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("as_of_date", models.DateField(db_index=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("pending_approval", "Pending approval"), ("approved", "Approved"), ("rejected", "Rejected"), ("applied", "Applied")], db_index=True, default="pending_approval", max_length=20)),
                ("score", models.DecimalField(decimal_places=4, max_digits=8)),
                ("score_breakdown", models.JSONField()),
                ("source_data_snapshot", models.JSONField()),
                ("policy_snapshot", models.JSONField()),
                ("proposed_min", models.DecimalField(decimal_places=2, max_digits=16)),
                ("proposed_midpoint", models.DecimalField(decimal_places=2, max_digits=16)),
                ("proposed_max", models.DecimalField(decimal_places=2, max_digits=16)),
                ("proposed_adjustment", models.DecimalField(decimal_places=2, max_digits=16)),
                ("currency", models.CharField(max_length=3, validators=[apps.organizations.validators.validate_currency])),
                ("explanation", models.TextField()),
                ("controls", models.JSONField(default=dict)),
                ("pay_equity_reviewed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_comp_recs", to=settings.AUTH_USER_MODEL)),
                ("current_salary", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="compensation_recommendations", to="employees.salary")),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="compensation_recommendations", to="employees.employee")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recommendations", to="compensation.compensationpolicy")),
                ("resulting_salary", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="source_recommendation", to="employees.salary")),
            ],
            options={"indexes": [models.Index(fields=["employee", "as_of_date", "created_at"], name="comp_rec_employee_date_idx"), models.Index(fields=["policy", "status"], name="comp_rec_policy_status_idx")]},
        ),
        migrations.CreateModel(
            name="CompensationApproval",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("approved", "Approved"), ("rejected", "Rejected"), ("applied", "Applied")], max_length=20)),
                ("actor_role", models.CharField(max_length=32)),
                ("explanation", models.TextField(blank=True)),
                ("snapshot", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="compensation_approvals", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
                ("recommendation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="approvals", to="compensation.compensationrecommendation")),
            ],
            options={"indexes": [models.Index(fields=["recommendation", "created_at"], name="comp_approval_rec_created_idx")]},
        ),
    ]
