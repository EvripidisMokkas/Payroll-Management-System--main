from django.contrib import admin

from .models import AuditAnnotation, AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "organization", "actor", "action", "object_type", "object_id", "is_sensitive_access")
    list_filter = ("action", "is_sensitive_access", "organization")
    search_fields = ("object_type", "object_id", "object_label", "request_id", "integrity_hash")
    readonly_fields = tuple(field.name for field in AuditEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditAnnotation)
class AuditAnnotationAdmin(admin.ModelAdmin):
    readonly_fields = ("organization", "author", "note", "created_at")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
