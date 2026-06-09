"""Pluggable tax-engine interface and strict jurisdiction resolution."""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

from django.core.exceptions import ImproperlyConfigured, ValidationError

from apps.security.legal import require_approved_jurisdiction
from apps.taxation.models import Jurisdiction, RuleStatus, TaxRuleVersion


class UnsupportedJurisdictionError(ImproperlyConfigured):
    """Raised rather than silently calculating with rules from another jurisdiction."""


@dataclass(frozen=True)
class TaxCalculationRequest:
    jurisdiction_code: str
    pay_date: date
    taxable_wages: Decimal
    year_to_date_wages: Decimal = Decimal("0")
    filing_status: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaxCalculationResult:
    employee_tax: Decimal
    employer_tax: Decimal
    jurisdiction_code: str
    rule_version: str
    explanation: dict[str, Any] = field(default_factory=dict)


class TaxCalculator(Protocol):
    def calculate(self, request: TaxCalculationRequest, rule: TaxRuleVersion) -> TaxCalculationResult: ...


class TaxEngineRegistry:
    def __init__(self):
        self._calculators: dict[str, TaxCalculator] = {}

    def register(self, key: str, calculator: TaxCalculator) -> None:
        self._calculators[key] = calculator

    def resolve(self, jurisdiction: Jurisdiction) -> TaxCalculator:
        if not jurisdiction.supported or not jurisdiction.calculator_key:
            raise UnsupportedJurisdictionError(
                f"Jurisdiction {jurisdiction.code} is not configured for payroll tax calculations."
            )
        try:
            return self._calculators[jurisdiction.calculator_key]
        except KeyError as exc:
            raise UnsupportedJurisdictionError(
                f"Tax calculator '{jurisdiction.calculator_key}' for {jurisdiction.code} is not registered."
            ) from exc


registry = TaxEngineRegistry()


def active_rule_for(jurisdiction: Jurisdiction, on_date: date) -> TaxRuleVersion:
    rules = (
        jurisdiction.rule_versions.filter(status=RuleStatus.ACTIVE, effective_from__lte=on_date)
        .filter(models_q_effective(on_date))
        .order_by("-effective_from", "-id")
    )
    rule = rules.first()
    if not rule:
        raise UnsupportedJurisdictionError(
            f"No active tax rule exists for {jurisdiction.code} on {on_date.isoformat()}."
        )
    return rule


def models_q_effective(on_date):
    from django.db import models

    return models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=on_date)


def calculate(request: TaxCalculationRequest) -> TaxCalculationResult:
    require_approved_jurisdiction(request.jurisdiction_code, "tax")
    try:
        jurisdiction = Jurisdiction.objects.get(code=request.jurisdiction_code)
    except Jurisdiction.DoesNotExist as exc:
        raise UnsupportedJurisdictionError(f"Unknown tax jurisdiction: {request.jurisdiction_code}.") from exc
    rule = active_rule_for(jurisdiction, request.pay_date)
    return registry.resolve(jurisdiction).calculate(request, rule)


def calculate_contribution(
    *, wages, year_to_date_wages, rate, annual_wage_base=None, year_to_date_contribution=Decimal("0"), annual_limit=None
):
    """Apply wage bases and annual limits without crossing either boundary."""
    wages = Decimal(wages)
    taxable = wages
    if annual_wage_base is not None:
        taxable = max(Decimal("0"), min(wages, Decimal(annual_wage_base) - Decimal(year_to_date_wages)))
    contribution = taxable * Decimal(rate)
    if annual_limit is not None:
        contribution = max(Decimal("0"), min(contribution, Decimal(annual_limit) - Decimal(year_to_date_contribution)))
    return contribution.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class TableTaxCalculator:
    """Generic progressive-bracket calculator suitable for imported table rules."""

    @staticmethod
    def money(value):
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def calculate(self, request: TaxCalculationRequest, rule: TaxRuleVersion) -> TaxCalculationResult:
        filing_status = rule.filing_statuses.filter(code=request.filing_status).first()
        brackets = rule.brackets.filter(filing_status=filing_status).order_by("lower_bound")
        if not brackets.exists():
            brackets = rule.brackets.filter(filing_status__isnull=True).order_by("lower_bound")
        if not brackets.exists():
            raise ValidationError(f"Rule {rule.version} has no brackets for filing status {request.filing_status}.")
        tax = Decimal("0")
        details = []
        for bracket in brackets:
            if request.taxable_wages <= bracket.lower_bound:
                continue
            taxable = request.taxable_wages - bracket.lower_bound
            if bracket.upper_bound is not None:
                taxable = min(taxable, bracket.upper_bound - bracket.lower_bound)
            amount = taxable * bracket.rate + bracket.fixed_amount
            tax += amount
            details.append(
                {"lower_bound": str(bracket.lower_bound), "taxable": str(taxable), "rate": str(bracket.rate)}
            )
        employer_tax = sum(
            min(request.taxable_wages, item.wage_base or request.taxable_wages) * item.rate + item.fixed_amount
            for item in rule.employer_taxes.all()
        )
        return TaxCalculationResult(
            employee_tax=self.money(tax),
            employer_tax=self.money(employer_tax),
            jurisdiction_code=rule.jurisdiction.code,
            rule_version=rule.version,
            explanation={"brackets": details},
        )


registry.register("table", TableTaxCalculator())
