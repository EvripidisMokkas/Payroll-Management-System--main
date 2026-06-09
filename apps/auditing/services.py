"""Audit recording and integrity-preserving export services."""

import csv
import hashlib
import io
import ipaddress
import json

from django.db import transaction
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .models import AuditAction, AuditEvent


def _request_context(request):
    if request is None:
        return "", None
    request_id = request.headers.get("X-Request-ID", "")[:100]
    forwarded = request.headers.get("X-Forwarded-For", "")
    source = (forwarded.split(",", 1)[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None
    try:
        source = str(ipaddress.ip_address(source)) if source else None
    except ValueError:
        source = None
    return request_id, source


@transaction.atomic
def record_event(
    *,
    organization,
    action,
    object_type,
    actor=None,
    object_id="",
    object_label="",
    before=None,
    after=None,
    request=None,
    sensitive=False,
):
    """Append one audit event. Call for creates, changes, approvals, deletes, exports, and sensitive reads."""
    request_id, source_address = _request_context(request)
    return AuditEvent.objects.create(
        organization=organization,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id or ""),
        object_label=str(object_label or "")[:255],
        before_summary=before or {},
        after_summary=after or {},
        request_id=request_id,
        source_address=source_address,
        is_sensitive_access=sensitive,
    )


def record_sensitive_access(*, organization, actor, instance, request=None, details=None):
    return record_event(
        organization=organization,
        actor=actor,
        action=AuditAction.ACCESS,
        object_type=instance._meta.label,
        object_id=instance.pk,
        object_label=str(instance),
        after=details or {},
        request=request,
        sensitive=True,
    )


def _event_rows(queryset):
    for event in queryset.order_by("occurred_at", "pk"):
        yield {
            "id": event.pk,
            "occurred_at": event.occurred_at.isoformat(),
            "actor_id": event.actor_id,
            "action": event.action,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "before_summary": event.before_summary,
            "after_summary": event.after_summary,
            "request_id": event.request_id,
            "source_address": event.source_address,
            "is_sensitive_access": event.is_sensitive_access,
            "previous_hash": event.previous_hash,
            "integrity_hash": event.integrity_hash,
        }


def export_audit_events(queryset, export_format):
    """Return bytes and integrity metadata for an already-authorized, filtered queryset."""
    rows = list(_event_rows(queryset))
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str).encode()
    metadata = {"record_count": len(rows), "sha256": hashlib.sha256(canonical).hexdigest()}
    if export_format == "json":
        return (
            json.dumps({"integrity": metadata, "events": rows}, indent=2, default=str).encode(),
            "application/json",
            metadata,
        )
    if export_format == "csv":
        output = io.StringIO()
        fields = list(rows[0]) if rows else ["id", "occurred_at", "action", "integrity_hash"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True) if isinstance(value, dict) else value
                    for key, value in row.items()
                }
            )
        return output.getvalue().encode(), "text/csv", metadata
    if export_format == "pdf":
        output = io.BytesIO()
        pdf = canvas.Canvas(output, pagesize=letter)
        y = 750
        pdf.drawString(40, y, f"Audit report — records: {metadata['record_count']} — SHA-256: {metadata['sha256']}")
        for row in rows:
            y -= 18
            if y < 40:
                pdf.showPage()
                y = 750
            pdf.drawString(
                40, y, f"{row['occurred_at'][:19]} | {row['action']} | {row['object_type']}:{row['object_id']}"
            )
        pdf.save()
        return output.getvalue(), "application/pdf", metadata
    raise ValueError("Unsupported audit export format.")
