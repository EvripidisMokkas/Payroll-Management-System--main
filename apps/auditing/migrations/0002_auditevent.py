from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("auditing", "0001_initial"), ("organizations", "0002_organization_legal_billing_lifecycle"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("access", "Access"), ("create", "Create"), ("update", "Update"), ("approve", "Approve"), ("delete", "Delete"), ("export", "Export"), ("redact", "Redact"), ("legal_hold", "Legal hold"), ("retention", "Retention")], db_index=True, max_length=32)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now, editable=False)),
                ("object_type", models.CharField(db_index=True, max_length=200)),
                ("object_id", models.CharField(blank=True, db_index=True, max_length=200)),
                ("object_label", models.CharField(blank=True, max_length=255)),
                ("before_summary", models.JSONField(blank=True, default=dict)),
                ("after_summary", models.JSONField(blank=True, default=dict)),
                ("request_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("source_address", models.GenericIPAddressField(blank=True, null=True)),
                ("is_sensitive_access", models.BooleanField(db_index=True, default=False)),
                ("previous_hash", models.CharField(blank=True, max_length=64)),
                ("integrity_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")),
            ],
            options={"ordering": ("occurred_at", "pk"), "permissions": [("export_audit", "Can export authorized audit records")]},
        ),
        migrations.AddIndex(model_name="auditevent", index=models.Index(fields=["organization", "action", "occurred_at"], name="audit_org_action_time_idx")),
    ]
