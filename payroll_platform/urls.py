"""Root URL configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.views import SecureLoginView
from payroll_platform.views import dashboard, health_check, home, workspace_domain, workspace_record_form

urlpatterns = [
    path("", home, name="home"),
    path("login/", SecureLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("workspace/<slug:domain_slug>/", workspace_domain, name="workspace-domain"),
    path("workspace/<slug:domain_slug>/new/", workspace_record_form, name="workspace-create"),
    path("workspace/<slug:domain_slug>/<int:record_id>/edit/", workspace_record_form, name="workspace-edit"),
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
    path("api/v1/", include("payroll_platform.api_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
