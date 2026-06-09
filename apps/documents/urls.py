"""URL routes for secure document operations."""

from django.urls import path

from .views import AttachmentUploadView, DocumentListCreateView, ProtectedAttachmentDownloadView

app_name = "documents"
urlpatterns = [
    path("organizations/<int:organization_id>/", DocumentListCreateView.as_view(), name="list-create"),
    path(
        "organizations/<int:organization_id>/<int:document_id>/attachments/",
        AttachmentUploadView.as_view(),
        name="upload",
    ),
    path(
        "organizations/<int:organization_id>/<int:document_id>/attachments/<int:attachment_id>/download/",
        ProtectedAttachmentDownloadView.as_view(),
        name="download",
    ),
]
