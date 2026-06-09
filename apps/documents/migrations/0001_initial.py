from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import apps.documents.models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("organizations", "0002_organization_legal_billing_lifecycle"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("category", models.CharField(choices=[("personal", "Personal record"), ("financial", "Financial record"), ("payroll", "Payroll"), ("tax", "Tax"), ("contract", "Contract"), ("other", "Other")], db_index=True, max_length=32)),
                ("access_classification", models.CharField(choices=[("internal", "Internal"), ("confidential", "Confidential"), ("highly_sensitive", "Highly sensitive")], db_index=True, default="confidential", max_length=32)),
                ("retention_until", models.DateField(blank=True, db_index=True, null=True)),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_documents", to=settings.AUTH_USER_MODEL)),
            ],
            options={"permissions": [("access_highly_sensitive_document", "Can access highly sensitive documents"), ("manage_document_retention", "Can manage document retention and legal holds"), ("export_document", "Can export authorized documents"), ("redact_document", "Can redact authorized documents")]},
        ),
        migrations.CreateModel(
            name="Attachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(max_length=500, storage=apps.documents.models.private_storage, upload_to=apps.documents.models.private_upload_key)),
                ("original_filename", models.CharField(max_length=255)),
                ("content_type", models.CharField(max_length=100)),
                ("size_bytes", models.PositiveBigIntegerField()),
                ("checksum_sha256", models.CharField(db_index=True, max_length=64)),
                ("malware_scan_status", models.CharField(default="clean", max_length=20)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attachments", to="documents.document")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
                ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="DocumentExport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("format", models.CharField(choices=[("json", "JSON manifest"), ("zip", "ZIP archive")], max_length=20)),
                ("status", models.CharField(choices=[("requested", "Requested"), ("approved", "Approved"), ("completed", "Completed"), ("rejected", "Rejected")], default="requested", max_length=20)),
                ("reason", models.TextField()),
                ("integrity_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="LegalHold",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.TextField()),
                ("placed_at", models.DateTimeField(auto_now_add=True)),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="legal_holds", to="documents.document")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
                ("placed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="placed_legal_holds", to=settings.AUTH_USER_MODEL)),
                ("released_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="released_legal_holds", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="RedactionRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fields", models.JSONField(default=list, help_text="Metadata fields or page regions approved for redaction.")),
                ("reason", models.TextField()),
                ("status", models.CharField(choices=[("requested", "Requested"), ("approved", "Approved"), ("completed", "Completed"), ("rejected", "Rejected")], default="requested", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="redactions_approved", to=settings.AUTH_USER_MODEL)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="redaction_requests", to="documents.document")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="redactions_requested", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(model_name="documentexport", name="documents", field=models.ManyToManyField(related_name="exports", to="documents.document")),
    ]
