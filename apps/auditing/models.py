"""Organization-scoped, append-only compliance audit records."""

import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.organizations.models import OrganizationScopedModel, OrganizationScopedQuerySet


class AuditAction(models.TextChoices):
    ACCESS = "access", "Access"
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    APPROVE = "approve", "Approve"
    DELETE = "delete", "Delete"
    EXPORT = "export", "Export"
    REDACT = "redact", "Redact"
    LEGAL_HOLD = "legal_hold", "Legal hold"
    RETENTION = "retention", "Retention"


class ImmutableAuditQuerySet(OrganizationScopedQuerySet):
    def update(self, **kwargs):
        raise ValidationError("Audit events are immutable.")

    def delete(self):
        raise ValidationError("Audit events are immutable.")


class AuditEvent(OrganizationScopedModel):
    """Tamper-evident event; application code cannot update or delete it."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=32, choices=AuditAction.choices, db_index=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)
    object_type = models.CharField(max_length=200, db_index=True)
    object_id = models.CharField(max_length=200, blank=True, db_index=True)
    object_label = models.CharField(max_length=255, blank=True)
    before_summary = models.JSONField(default=dict, blank=True)
    after_summary = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=100, blank=True, db_index=True)
    source_address = models.GenericIPAddressField(null=True, blank=True)
    is_sensitive_access = models.BooleanField(default=False, db_index=True)
    previous_hash = models.CharField(max_length=64, blank=True)
    integrity_hash = models.CharField(max_length=64, unique=True, editable=False)

    objects = ImmutableAuditQuerySet.as_manager()

    class Meta:
        ordering = ("occurred_at", "pk")
        indexes = [models.Index(fields=("organization", "action", "occurred_at"), name="audit_org_action_time_idx")]
        permissions = [("export_audit", "Can export authorized audit records")]

    def _hash_payload(self):
        payload = {
            "organization": self.organization_id,
            "actor": self.actor_id,
            "action": self.action,
            "occurred_at": self.occurred_at,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "before": self.before_summary,
            "after": self.after_summary,
            "request_id": self.request_id,
            "source_address": self.source_address,
            "sensitive": self.is_sensitive_access,
            "previous_hash": self.previous_hash,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk or type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit events are immutable.")
        if not self.previous_hash:
            previous = type(self).objects.filter(organization_id=self.organization_id).order_by("-pk").first()
            self.previous_hash = previous.integrity_hash if previous else ""
        self.integrity_hash = self._hash_payload()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events are immutable.")


class AuditAnnotation(OrganizationScopedModel):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [("annotate_audit", "Can add authorized audit annotations")]
