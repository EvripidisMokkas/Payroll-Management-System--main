"""Organization-scoped finance APIs, including a labeled prediction interface."""

from datetime import date

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Organization
from apps.organizations.services import authorize

from .models import ForecastRun, LedgerEntry, MetricType
from .permissions import visible_categories
from .services.forecasting import create_prediction


class DomainStatusView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"domain": "finance", "status": "available"})


class OrganizationFinanceView(APIView):
    action = "finance.read"

    def organization(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id, is_active=True)
        authorize(request.user, organization, self.action)
        return organization


class LedgerSourceRecordsView(OrganizationFinanceView):
    """Inspect the scoped source records behind an authorized chart."""

    def get(self, request, organization_id):
        organization = self.organization(request, organization_id)
        entries = (
            LedgerEntry.objects.for_organization(organization)
            .filter(account__category__in=visible_categories(request.user, organization))
            .select_related("account", "product")
        )
        if request.query_params.get("ids"):
            entries = entries.filter(id__in=request.query_params["ids"].split(","))
        records = [
            {
                "id": entry.id,
                "date": entry.entry_date,
                "account": entry.account.name,
                "category": entry.account.category,
                "amount": entry.amount,
                "description": entry.description,
                "source_type": entry.source_type,
                "source_reference": entry.source_reference,
            }
            for entry in entries[:500]
        ]
        return Response({"organization_id": organization.id, "records": records})


class PredictionView(OrganizationFinanceView):
    action = "finance.forecast"

    def post(self, request, organization_id):
        organization = self.organization(request, organization_id)
        try:
            metric_type = request.data["metric_type"]
            if metric_type not in MetricType.values:
                raise ValidationError("Unknown metric type.")
            observations = [(date.fromisoformat(item["date"]), item["value"]) for item in request.data["observations"]]
            run = create_prediction(
                organization=organization,
                metric_type=metric_type,
                observations=observations,
                horizon=int(request.data.get("horizon", 3)),
                assumptions=request.data.get("assumptions", {}),
                created_by=request.user,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            message = exc.messages if isinstance(exc, ValidationError) else [str(exc)]
            return Response({"errors": message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self._serialize(run), status=status.HTTP_201_CREATED)

    def get(self, request, organization_id):
        organization = self.organization(request, organization_id)
        runs = (
            ForecastRun.objects.for_organization(organization).prefetch_related("points").order_by("-created_at")[:20]
        )
        return Response({"predictions": [self._serialize(run) for run in runs]})

    @staticmethod
    def _serialize(run):
        return {
            "label": "Prediction — not a guaranteed outcome",
            "id": run.id,
            "metric_type": run.metric_type,
            "model_version": run.model_version,
            "assumptions": run.assumptions,
            "source_data_dates": {"start": run.source_data_start, "end": run.source_data_end},
            "disclaimer": run.disclaimer,
            "points": [
                {
                    "date": point.forecast_date,
                    "predicted": point.predicted_value,
                    "confidence_low": point.confidence_low,
                    "confidence_high": point.confidence_high,
                }
                for point in run.points.all()
            ],
        }
