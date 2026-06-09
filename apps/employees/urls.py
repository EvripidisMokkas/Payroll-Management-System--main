"""URL routes for the employees domain."""

from django.urls import path

from .views import DomainStatusView

app_name = "employees"
urlpatterns = [path("", DomainStatusView.as_view(), name="status")]
