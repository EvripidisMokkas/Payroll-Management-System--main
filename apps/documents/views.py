"""Authorized document upload and protected delivery endpoints."""

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditing.models import AuditAction
from apps.auditing.services import record_event, record_sensitive_access
from apps.organizations.mixins import OrganizationAccessMixin
from apps.organizations.services import authorize

from .models import AccessClassification, Document
from .services.uploads import create_attachment


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = (
            "id",
            "title",
            "owner",
            "category",
            "access_classification",
            "retention_until",
            "metadata",
            "created_at",
        )
        read_only_fields = ("id", "owner", "created_at")


class DocumentListCreateView(OrganizationAccessMixin, APIView):
    required_action = "document.read"

    def get(self, request, organization_id):
        organization = self.get_organization()
        documents = (
            Document.objects.for_user(request.user).for_organization(organization).filter(archived_at__isnull=True)
        )
        return Response(DocumentSerializer(documents, many=True).data)

    def post(self, request, organization_id):
        organization = self.get_organization()
        authorize(request.user, organization, "document.write")
        serializer = DocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.save(organization=organization, owner=request.user)
        record_event(
            organization=organization,
            actor=request.user,
            action=AuditAction.CREATE,
            object_type=document._meta.label,
            object_id=document.pk,
            object_label=document.title,
            after=serializer.data,
            request=request,
        )
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class AttachmentUploadView(OrganizationAccessMixin, APIView):
    required_action = "document.write"

    def post(self, request, organization_id, document_id):
        organization = self.get_organization()
        document = get_object_or_404(Document.objects.for_user(request.user), pk=document_id, organization=organization)
        upload = request.FILES.get("file")
        if not upload:
            raise serializers.ValidationError({"file": "A file is required."})
        attachment = create_attachment(document=document, upload=upload, actor=request.user, request=request)
        return Response(
            {"id": attachment.pk, "checksum_sha256": attachment.checksum_sha256}, status=status.HTTP_201_CREATED
        )


class ProtectedAttachmentDownloadView(OrganizationAccessMixin, APIView):
    required_action = "document.read"

    def get(self, request, organization_id, document_id, attachment_id):
        organization = self.get_organization()
        document = get_object_or_404(Document.objects.for_user(request.user), pk=document_id, organization=organization)
        if document.access_classification == AccessClassification.HIGHLY_SENSITIVE:
            authorize(request.user, organization, "document.read_sensitive")
            record_sensitive_access(
                organization=organization,
                actor=request.user,
                instance=document,
                request=request,
                details={"attachment_id": attachment_id, "purpose": request.headers.get("X-Access-Purpose", "")[:255]},
            )
        attachment = get_object_or_404(document.attachments, pk=attachment_id, malware_scan_status="clean")
        response = FileResponse(
            attachment.file.open("rb"),
            content_type=attachment.content_type,
            as_attachment=True,
            filename=attachment.original_filename,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "no-store, private"
        return response
