"""URL routes for analytics dashboards."""

from django.urls import path

from .views import DashboardAPIView, dashboard

app_name = "analytics"
urlpatterns = [
    path("organizations/<int:organization_id>/dashboard/", DashboardAPIView.as_view(), name="dashboard-api"),
    path("organizations/<int:organization_id>/dashboard/view/", dashboard, name="dashboard"),
]
