"""URL routes for the compensation domain."""

from django.urls import path

from .views import DomainStatusView

app_name = "compensation"
urlpatterns = [path("", DomainStatusView.as_view(), name="status")]
