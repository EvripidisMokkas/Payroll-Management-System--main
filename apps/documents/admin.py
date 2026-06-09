"""Admin registrations for secure document records."""

from django.contrib import admin

from .models import Attachment, Document, DocumentExport, LegalHold, RedactionRequest


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    readonly_fields = (
        "file",
        "original_filename",
        "content_type",
        "size_bytes",
        "checksum_sha256",
        "malware_scan_status",
        "uploaded_by",
        "uploaded_at",
    )
    can_delete = False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "organization",
        "owner",
        "category",
        "access_classification",
        "retention_until",
        "created_at",
    )
    list_filter = ("category", "access_classification", "organization")
    search_fields = ("title",)
    inlines = [AttachmentInline]


@admin.register(LegalHold)
class LegalHoldAdmin(admin.ModelAdmin):
    list_display = ("document", "organization", "placed_by", "placed_at", "released_at")
    readonly_fields = ("placed_at",)


@admin.register(RedactionRequest)
class RedactionRequestAdmin(admin.ModelAdmin):
    list_display = ("document", "organization", "status", "requested_by", "approved_by", "created_at")


@admin.register(DocumentExport)
class DocumentExportAdmin(admin.ModelAdmin):
    list_display = ("organization", "requested_by", "format", "status", "created_at", "completed_at")
    readonly_fields = ("integrity_metadata",)
