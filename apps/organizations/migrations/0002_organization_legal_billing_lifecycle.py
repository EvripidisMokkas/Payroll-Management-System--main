import django.utils.timezone
from django.db import migrations, models

import apps.organizations.validators


class Migration(migrations.Migration):
    dependencies = [("organizations", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="legal_name",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="organization",
            name="registration_number",
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                unique=True,
                validators=[apps.organizations.validators.validate_identifier],
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="tax_identifier_reference",
            field=models.CharField(
                blank=True,
                help_text="Token or encrypted reference only; never store a plaintext tax identifier.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="jurisdiction",
            field=models.CharField(default="US", help_text="ISO 3166-1 alpha-2 country code.", max_length=2),
        ),
        migrations.AddField(
            model_name="organization",
            name="billing_email",
            field=models.EmailField(blank=True, default="", max_length=254),
            preserve_default=False,
        ),
        migrations.AddField(model_name="organization", name="billing_address", field=models.TextField(blank=True)),
        migrations.AddField(
            model_name="organization",
            name="default_currency",
            field=models.CharField(
                default="USD", max_length=3, validators=[apps.organizations.validators.validate_currency]
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("active", "Active"),
                    ("suspended", "Suspended"),
                    ("terminated", "Terminated"),
                    ("archived", "Archived"),
                ],
                db_index=True,
                default="draft",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="organization", name="archived_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="organization", name="retention_until", field=models.DateField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="organization",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(model_name="organization", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AlterField(
            model_name="organization", name="is_active", field=models.BooleanField(db_index=True, default=True)
        ),
        migrations.AddIndex(
            model_name="organization", index=models.Index(fields=["status", "legal_name"], name="org_status_legal_idx")
        ),
    ]
