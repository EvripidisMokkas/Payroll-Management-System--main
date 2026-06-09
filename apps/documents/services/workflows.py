"""Retention, legal-hold, redaction, and export workflows."""

import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditing.models import AuditAction
from apps.auditing.services import record_event
from apps.organizations.services import authorize

from ..models import DocumentExport, LegalHold, RedactionRequest, WorkflowStatus


@transaction.atomic
def place_legal_hold(*, document, actor, reason, request=None):
    authorize(actor, document.organization, "document.manage_retention")
    hold = LegalHold.objects.create(
        organization=document.organization, document=document, placed_by=actor, reason=reason
    )
    record_event(
        organization=document.organization,
        actor=actor,
        action=AuditAction.LEGAL_HOLD,
        object_type=document._meta.label,
        object_id=document.pk,
        after={"hold_id": hold.pk, "reason": reason},
        request=request,
    )
    return hold


@transaction.atomic
def release_legal_hold(*, hold, actor, request=None):
    authorize(actor, hold.organization, "document.manage_retention")
    if hold.released_at:
        raise ValidationError("Legal hold has already been released.")
    hold.released_at, hold.released_by = timezone.now(), actor
    hold.save(update_fields=("released_at", "released_by"))
    record_event(
        organization=hold.organization,
        actor=actor,
        action=AuditAction.LEGAL_HOLD,
        object_type=hold.document._meta.label,
        object_id=hold.document_id,
        after={"released_hold_id": hold.pk},
        request=request,
    )
    return hold


@transaction.atomic
def purge_expired_document(*, document, actor, request=None, today=None):
    authorize(actor, document.organization, "document.manage_retention")
    today = today or timezone.localdate()
    if document.is_on_legal_hold:
        raise ValidationError("A document on legal hold cannot be purged.")
    if not document.retention_until or document.retention_until > today:
        raise ValidationError("The document retention period has not expired.")
    checksums = list(document.attachments.values_list("checksum_sha256", flat=True))
    for attachment in document.attachments.all():
        attachment.file.delete(save=False)
    document.archived_at = timezone.now()
    document.metadata = {**document.metadata, "purged": True, "purged_attachment_checksums": checksums}
    document.save(update_fields=("archived_at", "metadata", "updated_at"))
    record_event(
        organization=document.organization,
        actor=actor,
        action=AuditAction.RETENTION,
        object_type=document._meta.label,
        object_id=document.pk,
        after={"purged": True, "checksums": checksums},
        request=request,
    )
    return document


def request_redaction(*, document, actor, fields, reason, request=None):
    authorize(actor, document.organization, "document.redact")
    redaction = RedactionRequest.objects.create(
        organization=document.organization, document=document, requested_by=actor, fields=fields, reason=reason
    )
    record_event(
        organization=document.organization,
        actor=actor,
        action=AuditAction.REDACT,
        object_type=document._meta.label,
        object_id=document.pk,
        after={"request_id": redaction.pk, "fields": fields},
        request=request,
    )
    return redaction


def approve_redaction(*, redaction, actor, request=None):
    authorize(actor, redaction.organization, "document.redact")
    if redaction.status != WorkflowStatus.REQUESTED:
        raise ValidationError("Only requested redactions can be approved.")
    redaction.status, redaction.approved_by = WorkflowStatus.APPROVED, actor
    redaction.save(update_fields=("status", "approved_by"))
    record_event(
        organization=redaction.organization,
        actor=actor,
        action=AuditAction.APPROVE,
        object_type=redaction._meta.label,
        object_id=redaction.pk,
        after={"status": redaction.status},
        request=request,
    )
    return redaction


def build_export_manifest(*, export: DocumentExport, actor, request=None):
    authorize(actor, export.organization, "document.export")
    if export.documents.exclude(organization=export.organization).exists():
        raise ValidationError("An export cannot include documents from another organization.")
    rows = [
        {
            "id": d.pk,
            "title": d.title,
            "category": d.category,
            "retention_until": d.retention_until,
            "attachments": list(d.attachments.values("checksum_sha256", "content_type", "size_bytes")),
        }
        for d in export.documents.all()
    ]
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str).encode()
    export.integrity_metadata = {"sha256": hashlib.sha256(canonical).hexdigest(), "record_count": len(rows)}
    export.status, export.completed_at = WorkflowStatus.COMPLETED, timezone.now()
    export.save(update_fields=("integrity_metadata", "status", "completed_at"))
    record_event(
        organization=export.organization,
        actor=actor,
        action=AuditAction.EXPORT,
        object_type=export._meta.label,
        object_id=export.pk,
        after=export.integrity_metadata,
        request=request,
    )
    return canonical


def complete_redaction(*, redaction, actor, redacted_attachment_ids, request=None):
    """Complete an approved redaction without placing redacted values in the audit trail."""
    authorize(actor, redaction.organization, "document.redact")
    if redaction.status != WorkflowStatus.APPROVED:
        raise ValidationError("Only approved redactions can be completed.")
    redaction.status, redaction.completed_at = WorkflowStatus.COMPLETED, timezone.now()
    redaction.save(update_fields=("status", "completed_at"))
    record_event(
        organization=redaction.organization,
        actor=actor,
        action=AuditAction.REDACT,
        object_type=redaction._meta.label,
        object_id=redaction.pk,
        after={"status": redaction.status, "redacted_attachment_ids": list(redacted_attachment_ids)},
        request=request,
    )
    return redaction
