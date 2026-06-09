# Generated for the auditable payroll domain.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.organizations.validators


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="payrollrecord",
            options={"permissions": [("operate_legacy_payroll", "Can create and update legacy payroll operations")]},
        ),
        migrations.CreateModel(
            name="PaySchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                (
                    "frequency",
                    models.CharField(
                        choices=[
                            ("weekly", "Weekly"),
                            ("biweekly", "Biweekly"),
                            ("semimonthly", "Semimonthly"),
                            ("monthly", "Monthly"),
                        ],
                        max_length=20,
                    ),
                ),
                ("periods_per_year", models.PositiveSmallIntegerField()),
                (
                    "currency",
                    models.CharField(
                        default="USD", max_length=3, validators=[apps.organizations.validators.validate_currency]
                    ),
                ),
                ("active", models.BooleanField(default=True)),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("organization", "name"), name="unique_pay_schedule_name")
                ]
            },
        ),
        migrations.CreateModel(
            name="PayrollPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("pay_date", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("validation", "Validation"),
                            ("approval", "Approval"),
                            ("locked", "Locked"),
                            ("paid", "Paid"),
                            ("corrected", "Corrected"),
                            ("archived", "Archived"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
                (
                    "schedule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="periods", to="payroll.payschedule"
                    ),
                ),
            ],
            options={
                "permissions": [
                    ("operate_payroll", "Can create and validate payroll operations"),
                    ("approve_payroll", "Can approve and lock payroll"),
                    ("mark_payroll_paid", "Can mark payroll paid"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("schedule", "period_start", "period_end"), name="unique_payroll_period"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("period_end__gte", models.F("period_start"))),
                        name="payroll_period_dates_valid",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="EmployeePayrollInput",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "input_type",
                    models.CharField(
                        choices=[
                            ("base_salary", "Base salary"),
                            ("hourly", "Hourly work"),
                            ("overtime", "Overtime"),
                            ("bonus", "Bonus"),
                            ("commission", "Commission"),
                            ("benefit", "Benefit"),
                            ("pre_tax_deduction", "Pre-tax deduction"),
                            ("post_tax_deduction", "Post-tax deduction"),
                            ("employer_cost", "Employer cost"),
                        ],
                        max_length=30,
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=255)),
                ("amount", models.DecimalField(decimal_places=4, default=0, max_digits=16)),
                ("quantity", models.DecimalField(decimal_places=4, default=1, max_digits=12)),
                ("rate", models.DecimalField(decimal_places=4, default=0, max_digits=16)),
                ("source_key", models.CharField(max_length=120)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payroll_inputs",
                        to="employees.employee",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
                (
                    "period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="employee_inputs",
                        to="payroll.payrollperiod",
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["period", "employee"], name="pay_input_period_employee_idx")],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("period", "employee", "source_key"), name="unique_payroll_input_source"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="CalculationRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rules_version", models.CharField(max_length=50)),
                ("idempotency_key", models.CharField(max_length=160)),
                ("input_snapshot", models.JSONField()),
                ("rules_snapshot", models.JSONField()),
                ("explanation", models.JSONField(default=dict)),
                ("gross_pay", models.DecimalField(decimal_places=2, max_digits=16)),
                ("pre_tax_deductions", models.DecimalField(decimal_places=2, max_digits=16)),
                ("post_tax_deductions", models.DecimalField(decimal_places=2, max_digits=16)),
                ("employer_costs", models.DecimalField(decimal_places=2, max_digits=16)),
                ("net_pay", models.DecimalField(decimal_places=2, max_digits=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "adjustment_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="adjustments",
                        to="payroll.calculationrun",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payroll_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
                (
                    "period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="calculation_runs",
                        to="payroll.payrollperiod",
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["period", "created_at"], name="pay_run_period_created_idx")],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "idempotency_key"), name="unique_payroll_run_idempotency"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="PayrollLineItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "input_type",
                    models.CharField(
                        choices=[
                            ("base_salary", "Base salary"),
                            ("hourly", "Hourly work"),
                            ("overtime", "Overtime"),
                            ("bonus", "Bonus"),
                            ("commission", "Commission"),
                            ("benefit", "Benefit"),
                            ("pre_tax_deduction", "Pre-tax deduction"),
                            ("post_tax_deduction", "Post-tax deduction"),
                            ("employer_cost", "Employer cost"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("earning", "Earning"),
                            ("benefit", "Benefit"),
                            ("pre_tax_deduction", "Pre-tax deduction"),
                            ("post_tax_deduction", "Post-tax deduction"),
                            ("employer_cost", "Employer cost"),
                        ],
                        max_length=30,
                    ),
                ),
                ("description", models.CharField(max_length=255)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=16)),
                ("explanation", models.JSONField(default=dict)),
                ("source_snapshot", models.JSONField(default=dict)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payroll_line_items",
                        to="employees.employee",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="line_items",
                        to="payroll.calculationrun",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PayrollApproval",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "from_status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("validation", "Validation"),
                            ("approval", "Approval"),
                            ("locked", "Locked"),
                            ("paid", "Paid"),
                            ("corrected", "Corrected"),
                            ("archived", "Archived"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "to_status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("validation", "Validation"),
                            ("approval", "Approval"),
                            ("locked", "Locked"),
                            ("paid", "Paid"),
                            ("corrected", "Corrected"),
                            ("archived", "Archived"),
                        ],
                        max_length=20,
                    ),
                ),
                ("actor_role", models.CharField(max_length=32)),
                ("explanation", models.TextField(blank=True)),
                ("snapshot", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payroll_approvals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
                (
                    "period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="approvals",
                        to="payroll.payrollperiod",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PayrollCorrection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "adjustment_run",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="correction",
                        to="payroll.calculationrun",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
                (
                    "original_period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="corrections",
                        to="payroll.payrollperiod",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payroll_corrections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Payslip",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gross_pay", models.DecimalField(decimal_places=2, max_digits=16)),
                ("net_pay", models.DecimalField(decimal_places=2, max_digits=16)),
                ("snapshot", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="payslips", to="employees.employee"
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payslips",
                        to="payroll.calculationrun",
                    ),
                ),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("run", "employee"), name="unique_run_employee_payslip")]
            },
        ),
        migrations.CreateModel(
            name="PaymentBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("idempotency_key", models.CharField(max_length=160)),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=16)),
                ("payment_count", models.PositiveIntegerField()),
                ("snapshot", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
                (
                    "period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payment_batches",
                        to="payroll.payrollperiod",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payment_batches",
                        to="payroll.calculationrun",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "idempotency_key"), name="unique_payment_batch_idempotency"
                    )
                ]
            },
        ),
    ]
