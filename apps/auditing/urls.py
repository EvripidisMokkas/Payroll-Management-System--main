from django.urls import path

from .views import AuditAnnotationListCreateView, AuditExportView

app_name = "auditing"
urlpatterns = [
    path(
        "organizations/<int:organization_id>/annotations/", AuditAnnotationListCreateView.as_view(), name="annotations"
    ),
    path("organizations/<int:organization_id>/exports/", AuditExportView.as_view(), name="export"),
]
