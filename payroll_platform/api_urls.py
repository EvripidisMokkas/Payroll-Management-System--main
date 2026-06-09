"""Versioned API routing for domain apps."""

from django.urls import include, path

urlpatterns = [
    path("accounts/", include("apps.accounts.urls")),
    path("organizations/", include("apps.organizations.urls")),
    path("employees/", include("apps.employees.urls")),
    path("compensation/", include("apps.compensation.urls")),
    path("clients/", include("apps.clients.urls")),
    path("payroll/", include("apps.payroll.urls")),
    path("taxation/", include("apps.taxation.urls")),
    path("finance/", include("apps.finance.urls")),
    path("documents/", include("apps.documents.urls")),
    path("auditing/", include("apps.auditing.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("risk/", include("apps.risk.urls")),
]
