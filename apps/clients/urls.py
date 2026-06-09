"""URL routes for the clients domain."""

from django.urls import path

from .views import DomainStatusView

app_name = "clients"
urlpatterns = [path("", DomainStatusView.as_view(), name="status")]
