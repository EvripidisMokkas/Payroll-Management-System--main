"""Clearly labeled, auditable time-series prediction interface."""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.finance.models import ForecastPoint, ForecastRun

MODEL_VERSION = "linear-trend-v1"
FORECAST_PRECISION = Decimal("0.0001")
ROUNDING_POLICY = ROUND_HALF_UP


def forecast_value(value):
    """Round persisted forecasts to their four-decimal storage precision."""
    return Decimal(str(value)).quantize(FORECAST_PRECISION, rounding=ROUNDING_POLICY)


@transaction.atomic
def create_prediction(*, organization, metric_type, observations, horizon, assumptions, created_by=None):
    """Persist a simple linear trend and explicit uncertainty; never represent it as guaranteed."""
    if len(observations) < 2:
        raise ValidationError("At least two dated observations are required for a prediction.")
    if horizon < 1 or horizon > 36:
        raise ValidationError("Prediction horizon must be between 1 and 36 periods.")
    observations = sorted(observations, key=lambda item: item[0])
    values = [Decimal(str(value)) for _, value in observations]
    slope = (values[-1] - values[0]) / Decimal(len(values) - 1)
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    deviation = max((abs(value - mean) for value in values), default=Decimal("0"))
    run = ForecastRun.objects.create(
        organization=organization,
        metric_type=metric_type,
        model_version=MODEL_VERSION,
        assumptions=assumptions,
        source_data_start=observations[0][0],
        source_data_end=observations[-1][0],
        created_by=created_by,
    )
    last_date = observations[-1][0]
    for step in range(1, horizon + 1):
        predicted = values[-1] + slope * step
        uncertainty = deviation * Decimal(step).sqrt()
        ForecastPoint.objects.create(
            organization=organization,
            run=run,
            forecast_date=last_date + timedelta(days=30 * step),
            predicted_value=forecast_value(predicted),
            confidence_low=forecast_value(predicted - uncertainty),
            confidence_high=forecast_value(predicted + uncertainty),
        )
    return run
