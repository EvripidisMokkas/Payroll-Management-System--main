"""URL routes for the risk domain."""

from django.urls import path

from .views import DomainStatusView

app_name = "risk"
urlpatterns = [path("", DomainStatusView.as_view(), name="status")]
