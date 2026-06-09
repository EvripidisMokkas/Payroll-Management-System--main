"""Admin registrations for finance records."""

from django.contrib import admin

from .models import (
    DataQualityWarning,
    FinancialAccount,
    FinancialMetric,
    ForecastPoint,
    ForecastRun,
    InsuranceClaim,
    InsurancePolicy,
    InvestmentFund,
    LedgerEntry,
    Product,
)

for model in (
    FinancialAccount,
    Product,
    InvestmentFund,
    InsurancePolicy,
    InsuranceClaim,
    LedgerEntry,
    FinancialMetric,
    DataQualityWarning,
    ForecastRun,
    ForecastPoint,
):
    admin.site.register(model)
