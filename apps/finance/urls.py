"""URL routes for the finance domain."""

from django.urls import path

from .views import DomainStatusView, LedgerSourceRecordsView, PredictionView

app_name = "finance"
urlpatterns = [
    path("", DomainStatusView.as_view(), name="status"),
    path(
        "organizations/<int:organization_id>/ledger-sources/", LedgerSourceRecordsView.as_view(), name="ledger-sources"
    ),
    path("organizations/<int:organization_id>/predictions/", PredictionView.as_view(), name="predictions"),
]
