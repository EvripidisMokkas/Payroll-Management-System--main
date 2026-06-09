"""Secure, organization-scoped document records and compliance workflows."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import storages
from django.db import models

from apps.organizations.models import OrganizationScopedModel


def private_storage():
    return storages["private"]


def private_upload_key(instance, filename):
    """Generate a non-guessable key without retaining the untrusted original filename."""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"organizations/{instance.document.organization_id}/{uuid.uuid4().hex[:2]}/{uuid.uuid4().hex}.{suffix[:10]}"


class AccessClassification(models.TextChoices):
    INTERNAL = "internal", "Internal"
    CONFIDENTIAL = "confidential", "Confidential"
    HIGHLY_SENSITIVE = "highly_sensitive", "Highly sensitive"


class DocumentCategory(models.TextChoices):
    PERSONAL = "personal", "Personal record"
    FINANCIAL = "financial", "Financial record"
    PAYROLL = "payroll", "Payroll"
    TAX = "tax", "Tax"
    CONTRACT = "contract", "Contract"
    OTHER = "other", "Other"


class Document(OrganizationScopedModel):
    title = models.CharField(max_length=255)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_documents")
    category = models.CharField(max_length=32, choices=DocumentCategory.choices, db_index=True)
    access_classification = models.CharField(
        max_length=32, choices=AccessClassification.choices, default=AccessClassification.CONFIDENTIAL, db_index=True
    )
    retention_until = models.DateField(null=True, blank=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [
            ("access_highly_sensitive_document", "Can access highly sensitive documents"),
            ("manage_document_retention", "Can manage document retention and legal holds"),
            ("export_document", "Can export authorized documents"),
            ("redact_document", "Can redact authorized documents"),
        ]

    def __str__(self):
        return self.title

    @property
    def is_on_legal_hold(self):
        return self.legal_holds.filter(released_at__isnull=True).exists()


class Attachment(OrganizationScopedModel):
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="attachments")
    file = models.FileField(storage=private_storage, upload_to=private_upload_key, max_length=500)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField()
    checksum_sha256 = models.CharField(max_length=64, db_index=True)
    malware_scan_status = models.CharField(max_length=20, default="clean")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.document_id and self.organization_id != self.document.organization_id:
            raise ValidationError({"document": "Document must belong to the same organization."})


class LegalHold(OrganizationScopedModel):
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="legal_holds")
    reason = models.TextField()
    placed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="placed_legal_holds")
    placed_at = models.DateTimeField(auto_now_add=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="released_legal_holds"
    )
    released_at = models.DateTimeField(null=True, blank=True)


class WorkflowStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    APPROVED = "approved", "Approved"
    COMPLETED = "completed", "Completed"
    REJECTED = "rejected", "Rejected"


class RedactionRequest(OrganizationScopedModel):
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="redaction_requests")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="redactions_requested"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="redactions_approved"
    )
    fields = models.JSONField(default=list, help_text="Metadata fields or page regions approved for redaction.")
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class DocumentExport(OrganizationScopedModel):
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    documents = models.ManyToManyField(Document, related_name="exports")
    format = models.CharField(max_length=20, choices=(("json", "JSON manifest"), ("zip", "ZIP archive")))
    status = models.CharField(max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.REQUESTED)
    reason = models.TextField()
    integrity_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
