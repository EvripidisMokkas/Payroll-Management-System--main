"""Role-tailored, organization-scoped analytics dashboards."""

from datetime import timedelta

from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.models import DataQualityWarning, LedgerEntry
from apps.finance.permissions import visible_categories
from apps.finance.services.calculations import calculate_metrics
from apps.organizations.models import Organization, OrganizationRole
from apps.organizations.services import authorize, membership_for

ROLE_METRICS = {
    OrganizationRole.ADMINISTRATOR: ["gross_profit", "operating_profit", "after_tax_result", "payroll_revenue_ratio"],
    OrganizationRole.AUDITOR: ["gross_profit", "operating_profit", "after_tax_result", "coverage_margin"],
    OrganizationRole.CLIENT: ["gross_profit", "coverage_margin"],
    OrganizationRole.EMPLOYEE: [],
    OrganizationRole.PAYROLL_OPERATOR: ["payroll_revenue_ratio"],
}


def dashboard_payload(user, organization):
    membership = membership_for(user, organization)
    role = OrganizationRole.ADMINISTRATOR if user.is_superuser else membership.role
    end = timezone.localdate()
    start = end - timedelta(days=365)
    entries = LedgerEntry.objects.for_organization(organization).filter(
        entry_date__range=(start, end), account__category__in=visible_categories(user, organization)
    )
    metrics = calculate_metrics(organization, start, end)
    entry_ids = list(entries.values_list("id", flat=True))
    source_url = reverse("finance:ledger-sources", kwargs={"organization_id": organization.id})
    visible = ROLE_METRICS[role]
    charts = [
        {
            "title": metric.replace("_", " ").title(),
            "metric": metric,
            "value": metrics[metric],
            "source_count": len(entry_ids),
            "source_url": f"{source_url}?ids={','.join(map(str, entry_ids))}",
        }
        for metric in visible
    ]
    warnings = []
    if role in {OrganizationRole.ADMINISTRATOR, OrganizationRole.AUDITOR}:
        warnings = list(
            DataQualityWarning.objects.for_organization(organization)
            .filter(resolved_at__isnull=True)
            .values("code", "message", "source_reference")
        )
    if not entries.exists():
        warnings.append({"code": "NO_SOURCE_DATA", "message": "No ledger source data is available for this period."})
    return {"organization": organization, "role": role, "charts": charts, "warnings": warnings}


class DashboardAPIView(APIView):
    def get(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id, is_active=True)
        authorize(request.user, organization, "analytics.read")
        payload = dashboard_payload(request.user, organization)
        payload["organization"] = {"id": organization.id, "name": organization.name}
        return Response(payload)


def dashboard(request, organization_id):
    organization = get_object_or_404(Organization, pk=organization_id, is_active=True)
    authorize(request.user, organization, "analytics.read")
    return render(request, "analytics/dashboard.html", dashboard_payload(request.user, organization))
