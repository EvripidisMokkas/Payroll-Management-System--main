"""Upload validation, malware scanning, and secure attachment creation."""

import hashlib
import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.auditing.models import AuditAction
from apps.auditing.services import record_event
from apps.organizations.services import authorize

from ..models import Attachment

DEFAULT_ALLOWED_TYPES = {
    "application/pdf": (".pdf", b"%PDF-"),
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": ((".jpg", ".jpeg"), b"\xff\xd8\xff"),
    "text/plain": (".txt", None),
    "text/csv": (".csv", None),
}
DANGEROUS_SIGNATURES = (b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR", b"<script", b"<?php", b"MZ")


def validate_and_scan(upload):
    max_size = getattr(settings, "DOCUMENT_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
    if upload.size > max_size:
        raise ValidationError(f"File exceeds the {max_size}-byte upload limit.")
    supplied_type = (getattr(upload, "content_type", "") or "").lower()
    extension = Path(upload.name).suffix.lower()
    guessed_type = mimetypes.guess_type(upload.name)[0]
    rules = DEFAULT_ALLOWED_TYPES.get(supplied_type)
    if not rules or guessed_type != supplied_type:
        raise ValidationError("File type or extension is not allowed.")
    extensions, magic = rules
    if isinstance(extensions, str):
        extensions = (extensions,)
    if extension not in extensions:
        raise ValidationError("File extension does not match its declared type.")
    content = upload.read()
    upload.seek(0)
    if magic and not content.startswith(magic):
        raise ValidationError("File content does not match its declared type.")
    lowered = content.lower()
    if any(signature.lower() in lowered for signature in DANGEROUS_SIGNATURES):
        raise ValidationError("Upload rejected by malware/content scan.")
    return hashlib.sha256(content).hexdigest(), supplied_type


@transaction.atomic
def create_attachment(*, document, upload, actor, request=None):
    authorize(actor, document.organization, "document.write")
    checksum, content_type = validate_and_scan(upload)
    attachment = Attachment(
        organization=document.organization,
        document=document,
        file=upload,
        original_filename=Path(upload.name).name[:255],
        content_type=content_type,
        size_bytes=upload.size,
        checksum_sha256=checksum,
        malware_scan_status="clean",
        uploaded_by=actor,
    )
    attachment.full_clean()
    attachment.save()
    record_event(
        organization=document.organization,
        actor=actor,
        action=AuditAction.CREATE,
        object_type=attachment._meta.label,
        object_id=attachment.pk,
        object_label=attachment.original_filename,
        after={"checksum_sha256": checksum, "content_type": content_type, "size_bytes": upload.size},
        request=request,
    )
    return attachment
