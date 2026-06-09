"""Read-only audit feed, controlled exports, and append-only annotations."""

from django.http import HttpResponse
from django.utils.dateparse import parse_datetime
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from apps.organizations.mixins import OrganizationAccessMixin
from apps.organizations.services import authorize

from .models import AuditAnnotation, AuditEvent
from .services import export_audit_events, record_event


class AuditAnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditAnnotation
        fields = ("id", "author", "note", "created_at")
        read_only_fields = ("id", "author", "created_at")


class AuditAnnotationListCreateView(OrganizationAccessMixin, generics.ListCreateAPIView):
    serializer_class = AuditAnnotationSerializer
    required_action = "audit.read"

    def perform_create(self, serializer):
        organization = self.get_organization()
        authorize(self.request.user, organization, "audit.annotate")
        serializer.save(organization=organization, author=self.request.user)


class AuditExportView(OrganizationAccessMixin, APIView):
    required_action = "audit.export"

    def get(self, request, organization_id):
        organization = self.get_organization()
        queryset = AuditEvent.objects.for_user(request.user).for_organization(organization)
        if action := request.query_params.get("action"):
            queryset = queryset.filter(action=action)
        if object_type := request.query_params.get("object_type"):
            queryset = queryset.filter(object_type=object_type)
        if request.query_params.get("sensitive") in {"true", "false"}:
            queryset = queryset.filter(is_sensitive_access=request.query_params["sensitive"] == "true")
        for parameter, lookup in (("from", "occurred_at__gte"), ("to", "occurred_at__lte")):
            if raw := request.query_params.get(parameter):
                parsed = parse_datetime(raw)
                if not parsed:
                    raise ValidationError({parameter: "Use an ISO-8601 timestamp."})
                queryset = queryset.filter(**{lookup: parsed})
        export_format = request.query_params.get("format", "json").lower()
        try:
            content, content_type, metadata = export_audit_events(queryset, export_format)
        except ValueError as exc:
            raise ValidationError({"format": str(exc)}) from exc
        record_event(
            organization=organization,
            actor=request.user,
            action="export",
            object_type="auditing.AuditEvent",
            after={"filters": request.query_params.dict(), **metadata},
            request=request,
        )
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="audit-report.{export_format}"'
        response["X-Report-SHA256"] = metadata["sha256"]
        response["X-Report-Record-Count"] = str(metadata["record_count"])
        response["Cache-Control"] = "no-store, private"
        return response
