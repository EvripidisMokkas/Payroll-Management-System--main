from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.test import SimpleTestCase, TestCase

from apps.compensation.services.recommendations import _money as compensation_money
from apps.finance.models import AccountCategory, LedgerEntry
from apps.finance.services.calculations import ROUNDING_POLICY as FINANCE_ROUNDING
from apps.finance.services.calculations import gross_profit, payroll_to_revenue_ratio
from apps.finance.services.calculations import money as finance_money
from apps.finance.services.forecasting import ROUNDING_POLICY as FORECAST_ROUNDING
from apps.finance.services.forecasting import forecast_value
from apps.payroll.models import InputType
from apps.payroll.services.v1 import RULES_SNAPSHOT, calculate
from apps.payroll.services.v1 import money as payroll_money
from apps.taxation.services.engine import TableTaxCalculator, calculate_contribution
from tests import factories


class MonetaryPolicyUnitTests(SimpleTestCase):
    def test_every_calculation_boundary_uses_decimal_and_an_explicit_half_up_policy(self):
        self.assertEqual(RULES_SNAPSHOT["rounding"], "ROUND_HALF_UP")
        self.assertIs(FINANCE_ROUNDING, ROUND_HALF_UP)
        self.assertIs(FORECAST_ROUNDING, ROUND_HALF_UP)
        self.assertEqual(payroll_money(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(finance_money(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(compensation_money(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(TableTaxCalculator.money(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(forecast_value(Decimal("1.00005")), Decimal("1.0001"))

    def test_payroll_rounds_each_component_before_totals(self):
        result = calculate(
            [
                {"employee_id": 1, "input_type": InputType.HOURLY, "rate": "10.005", "quantity": "1"},
                {"employee_id": 1, "input_type": InputType.POST_TAX_DEDUCTION, "amount": "0.005"},
            ]
        )
        self.assertEqual(result["gross_pay"], Decimal("10.01"))
        self.assertEqual(result["post_tax_deductions"], Decimal("0.01"))
        self.assertEqual(result["net_pay"], Decimal("10.00"))

    def test_tax_contribution_rounds_half_up_after_caps(self):
        self.assertEqual(calculate_contribution(wages="10.05", year_to_date_wages="0", rate="0.10"), Decimal("1.01"))


class FinanceCalculationPolicyTests(TestCase):
    def test_finance_money_and_ratio_outputs_are_quantized(self):
        tenant = factories.organization()
        factories.ledger_entry(tenant=tenant, category=AccountCategory.REVENUE, amount=Decimal("3.00"))
        factories.ledger_entry(tenant=tenant, category=AccountCategory.OPERATING_COST, amount=Decimal("1.00"))
        factories.ledger_entry(tenant=tenant, category=AccountCategory.PAYROLL_COST, amount=Decimal("1.00"))
        entries = LedgerEntry.objects.for_organization(tenant).filter(entry_date=date(2026, 1, 31))

        self.assertEqual(gross_profit(entries), Decimal("2.00"))
        self.assertEqual(payroll_to_revenue_ratio(entries), Decimal("33.3333"))
