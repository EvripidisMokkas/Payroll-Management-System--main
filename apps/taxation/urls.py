"""URL routes for the taxation domain."""

from django.urls import path

from .views import DomainStatusView

app_name = "taxation"
urlpatterns = [path("", DomainStatusView.as_view(), name="status")]
