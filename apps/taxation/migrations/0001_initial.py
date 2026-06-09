import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("organizations", "0002_organization_legal_billing_lifecycle"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="Jurisdiction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, unique=True)),
                ("name", models.CharField(max_length=160)),
                ("country_code", models.CharField(max_length=2)),
                ("calculator_key", models.CharField(blank=True, max_length=120)),
                ("supported", models.BooleanField(default=False)),
                ("filing_export_formats", models.JSONField(blank=True, default=list)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="children",
                        to="taxation.jurisdiction",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TaxRuleVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.CharField(max_length=80)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("validated", "Validated"),
                            ("approved", "Approved"),
                            ("active", "Active"),
                            ("retired", "Retired"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("source", models.CharField(blank=True, max_length=255)),
                ("source_checksum", models.CharField(blank=True, max_length=64)),
                ("imported_payload", models.JSONField(blank=True, default=dict)),
                ("validation_errors", models.JSONField(blank=True, default=list)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="approved_tax_rules",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "jurisdiction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rule_versions",
                        to="taxation.jurisdiction",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["jurisdiction", "status", "effective_from"], name="tax_rule_resolution_idx")
                ]
            },
        ),
        migrations.CreateModel(
            name="TaxYear",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveSmallIntegerField()),
                ("starts_on", models.DateField()),
                ("ends_on", models.DateField()),
                (
                    "rule_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tax_years",
                        to="taxation.taxruleversion",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="FilingStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=40)),
                ("name", models.CharField(max_length=120)),
                (
                    "rule_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="filing_statuses",
                        to="taxation.taxruleversion",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TaxBracket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("lower_bound", models.DecimalField(decimal_places=4, max_digits=18)),
                ("upper_bound", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("rate", models.DecimalField(decimal_places=6, max_digits=8)),
                ("fixed_amount", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                (
                    "filing_status",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="brackets",
                        to="taxation.filingstatus",
                    ),
                ),
                (
                    "rule_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="brackets",
                        to="taxation.taxruleversion",
                    ),
                ),
            ],
            options={"ordering": ("lower_bound",)},
        ),
        migrations.CreateModel(
            name="Allowance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=60)),
                ("amount", models.DecimalField(decimal_places=4, max_digits=18)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "filing_status",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="taxation.filingstatus"
                    ),
                ),
                (
                    "rule_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="allowances",
                        to="taxation.taxruleversion",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ContributionLimit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=60)),
                ("employee_rate", models.DecimalField(decimal_places=6, default=0, max_digits=8)),
                ("employer_rate", models.DecimalField(decimal_places=6, default=0, max_digits=8)),
                ("annual_wage_base", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("annual_employee_limit", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("annual_employer_limit", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                (
                    "rule_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contribution_limits",
                        to="taxation.taxruleversion",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="EmployerTax",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=60)),
                ("rate", models.DecimalField(decimal_places=6, max_digits=8)),
                ("wage_base", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("fixed_amount", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                (
                    "rule_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="employer_taxes",
                        to="taxation.taxruleversion",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="OrganizationTaxConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("required", models.BooleanField(default=True)),
                ("external_provider_key", models.CharField(blank=True, max_length=120)),
                ("active", models.BooleanField(default=True)),
                (
                    "jurisdiction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="organization_configurations",
                        to="taxation.jurisdiction",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="FilingPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period_type", models.CharField(max_length=30)),
                ("starts_on", models.DateField()),
                ("ends_on", models.DateField()),
                ("due_on", models.DateField()),
                ("status", models.CharField(default="open", max_length=20)),
                (
                    "jurisdiction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="filing_periods",
                        to="taxation.jurisdiction",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TaxLiability",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("liability_type", models.CharField(max_length=60)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=18)),
                ("payment_reference", models.CharField(blank=True, max_length=160)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("source_calculation_ids", models.JSONField(blank=True, default=list)),
                (
                    "filing_period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="liabilities",
                        to="taxation.filingperiod",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
                (
                    "rule_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="liabilities",
                        to="taxation.taxruleversion",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="FilingAmendment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveSmallIntegerField()),
                ("reason", models.TextField()),
                ("status", models.CharField(default="draft", max_length=20)),
                ("replaces_reference", models.CharField(blank=True, max_length=160)),
                ("submitted_reference", models.CharField(blank=True, max_length=160)),
                ("changes", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "filing_period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="amendments",
                        to="taxation.filingperiod",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="FilingExport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("format", models.CharField(max_length=40)),
                ("payload", models.TextField()),
                ("checksum", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "amendment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="exports",
                        to="taxation.filingamendment",
                    ),
                ),
                (
                    "filing_period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="exports", to="taxation.filingperiod"
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="taxruleversion",
            constraint=models.UniqueConstraint(fields=("jurisdiction", "version"), name="unique_tax_rule_version"),
        ),
        migrations.AddConstraint(
            model_name="taxruleversion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("effective_to__isnull", True), ("effective_to__gte", models.F("effective_from")), _connector="OR"
                ),
                name="tax_rule_effective_dates_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="taxbracket",
            constraint=models.CheckConstraint(
                condition=models.Q(("lower_bound__gte", 0)), name="tax_bracket_lower_nonnegative"
            ),
        ),
        migrations.AddConstraint(
            model_name="taxbracket",
            constraint=models.CheckConstraint(
                condition=models.Q(("rate__gte", 0)), name="tax_bracket_rate_nonnegative"
            ),
        ),
        migrations.AddConstraint(
            model_name="taxbracket",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("upper_bound__isnull", True), ("upper_bound__gt", models.F("lower_bound")), _connector="OR"
                ),
                name="tax_bracket_bounds_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="taxyear",
            constraint=models.UniqueConstraint(fields=("rule_version", "year"), name="unique_rule_tax_year"),
        ),
        migrations.AddConstraint(
            model_name="filingstatus",
            constraint=models.UniqueConstraint(fields=("rule_version", "code"), name="unique_rule_filing_status"),
        ),
        migrations.AddConstraint(
            model_name="allowance",
            constraint=models.UniqueConstraint(fields=("rule_version", "code"), name="unique_rule_allowance"),
        ),
        migrations.AddConstraint(
            model_name="contributionlimit",
            constraint=models.UniqueConstraint(fields=("rule_version", "code"), name="unique_rule_contribution"),
        ),
        migrations.AddConstraint(
            model_name="employertax",
            constraint=models.UniqueConstraint(fields=("rule_version", "code"), name="unique_rule_employer_tax"),
        ),
        migrations.AddConstraint(
            model_name="organizationtaxconfiguration",
            constraint=models.UniqueConstraint(
                fields=("organization", "jurisdiction"), name="unique_org_tax_jurisdiction"
            ),
        ),
        migrations.AddConstraint(
            model_name="filingperiod",
            constraint=models.UniqueConstraint(
                fields=("organization", "jurisdiction", "period_type", "starts_on", "ends_on"),
                name="unique_tax_filing_period",
            ),
        ),
        migrations.AddConstraint(
            model_name="filingamendment",
            constraint=models.UniqueConstraint(fields=("filing_period", "sequence"), name="unique_filing_amendment"),
        ),
    ]
