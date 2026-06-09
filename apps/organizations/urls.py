"""URL routes for the organizations domain."""

from django.urls import path

from .views import DomainStatusView

app_name = "organizations"
urlpatterns = [path("", DomainStatusView.as_view(), name="status")]
