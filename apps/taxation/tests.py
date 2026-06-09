"""Fixture-based coverage for versioned taxation workflows."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import Employee
from apps.organizations.models import Organization, OrganizationMembership, OrganizationRole
from apps.payroll.models import EmployeePayrollInput, InputType, PayrollLifecycle, PayrollPeriod, PaySchedule
from apps.payroll.services import create_adjustment_run, process_payroll
from apps.taxation.models import (
    FilingAmendment,
    FilingPeriod,
    Jurisdiction,
    OrganizationTaxConfiguration,
    RuleStatus,
    TaxLiability,
)
from apps.taxation.services.engine import (
    TaxCalculationRequest,
    UnsupportedJurisdictionError,
    calculate,
    calculate_contribution,
)
from apps.taxation.services.filings import create_filing_export
from apps.taxation.services.imports import activate_rule, approve_rule, import_tax_table

User = get_user_model()
FIXTURE = Path(__file__).parent / "fixtures" / "tax_table_boundary.json"


class DomainStatusTests(TestCase):
    def test_status_endpoint(self):
        response = self.client.get(reverse("taxation:status"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["domain"], "taxation")


class TaxWorkflowTests(TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text())
        self.jurisdiction = Jurisdiction.objects.create(
            code="US-TEST",
            name="Test State",
            country_code="US",
            supported=True,
            calculator_key="table",
            filing_export_formats=["csv", "json"],
        )
        self.user = User.objects.create_user(username="approver", email="approver@example.com")

    def import_and_activate(self, payload=None):
        rule = import_tax_table(payload or self.payload, source="fixture")
        approve_rule(rule, actor=self.user)
        return activate_rule(rule)

    def test_import_requires_validation_approval_and_activation(self):
        invalid = {
            **self.payload,
            "version": "invalid",
            "brackets": [{"lower_bound": 10, "upper_bound": 5, "rate": 0.1}],
        }
        bad_rule = import_tax_table(invalid)
        self.assertEqual(bad_rule.status, RuleStatus.DRAFT)
        with self.assertRaises(ValidationError):
            approve_rule(bad_rule, actor=self.user)

        rule = import_tax_table(self.payload)
        self.assertEqual(rule.status, RuleStatus.VALIDATED)
        with self.assertRaises(ValidationError):
            activate_rule(rule)
        approve_rule(rule, actor=self.user)
        activate_rule(rule)
        self.assertEqual(rule.status, RuleStatus.ACTIVE)

    def test_fixture_boundary_values_use_expected_brackets(self):
        self.import_and_activate()
        at_boundary = calculate(
            TaxCalculationRequest("US-TEST", date(2026, 6, 1), Decimal("1000"), filing_status="single")
        )
        over_boundary = calculate(
            TaxCalculationRequest("US-TEST", date(2026, 6, 1), Decimal("1001"), filing_status="single")
        )
        self.assertEqual(at_boundary.employee_tax, Decimal("100.00"))
        self.assertEqual(over_boundary.employee_tax, Decimal("100.20"))
        self.assertEqual(over_boundary.rule_version, "2026.1")

    def test_yearly_contribution_limits_do_not_overrun(self):
        self.assertEqual(
            calculate_contribution(
                wages="5000",
                year_to_date_wages="98000",
                rate="0.10",
                annual_wage_base="100000",
                year_to_date_contribution="9800",
                annual_limit="10000",
            ),
            Decimal("200.00"),
        )

    def test_mid_period_rule_change_resolves_by_pay_date(self):
        first = self.import_and_activate()
        second_payload = {**self.payload, "version": "2026.2", "effective_from": "2026-07-01"}
        second = self.import_and_activate(second_payload)
        june = calculate(TaxCalculationRequest("US-TEST", date(2026, 6, 30), Decimal("100"), filing_status="single"))
        july = calculate(TaxCalculationRequest("US-TEST", date(2026, 7, 1), Decimal("100"), filing_status="single"))
        self.assertEqual((june.rule_version, july.rule_version), (first.version, second.version))

    def test_unsupported_jurisdiction_surfaces_configuration_error(self):
        Jurisdiction.objects.create(code="US-NOPE", name="Unsupported", country_code="US")
        with self.assertRaisesRegex(UnsupportedJurisdictionError, "not configured"):
            calculate(TaxCalculationRequest("US-NOPE", date(2026, 1, 1), Decimal("100")))
        with self.assertRaisesRegex(UnsupportedJurisdictionError, "Unknown"):
            calculate(TaxCalculationRequest("XX-MISSING", date(2026, 1, 1), Decimal("100")))

    def test_payroll_records_rule_provenance_and_retroactive_adjustment(self):
        self.import_and_activate()
        organization = Organization.objects.create(name="Payroll Org", slug="payroll-tax")
        OrganizationTaxConfiguration.objects.create(organization=organization, jurisdiction=self.jurisdiction)
        OrganizationMembership.objects.create(
            organization=organization, user=self.user, role=OrganizationRole.ADMINISTRATOR
        )
        schedule = PaySchedule.objects.create(
            organization=organization, name="Monthly", frequency="monthly", periods_per_year=12
        )
        period = PayrollPeriod.objects.create(
            organization=organization,
            schedule=schedule,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            pay_date=date(2026, 6, 1),
        )
        employee = Employee.objects.create(
            organization=organization,
            employee_number="T-1",
            given_name="Tax",
            family_name="Tester",
            hire_date=date(2026, 1, 1),
        )
        EmployeePayrollInput.objects.create(
            organization=organization,
            period=period,
            employee=employee,
            input_type=InputType.BASE_SALARY,
            amount="1000",
            source_key="salary",
        )
        original = process_payroll(period=period, idempotency_key="tax-original", actor=self.user)
        self.assertEqual(original.tax_jurisdiction_code, "US-TEST")
        self.assertEqual(original.tax_rule_version, "2026.1")

        PayrollPeriod.objects.filter(pk=period.pk).update(status=PayrollLifecycle.PAID)
        period.refresh_from_db()
        adjustment = create_adjustment_run(
            original_period=period,
            inputs=[{"employee_id": employee.pk, "input_type": InputType.BONUS, "amount": "-10"}],
            reason="Retroactive adjustment",
            idempotency_key="tax-adjustment",
            actor=self.user,
        )
        self.assertEqual(adjustment.tax_rule_version, original.tax_rule_version)
        self.assertEqual(adjustment.adjustment_of, original)

    def test_required_unsupported_configuration_blocks_payroll(self):
        organization = Organization.objects.create(name="Blocked Org", slug="blocked-tax")
        unsupported = Jurisdiction.objects.create(code="US-BLOCK", name="Blocked", country_code="US")
        OrganizationTaxConfiguration.objects.create(organization=organization, jurisdiction=unsupported)
        schedule = PaySchedule.objects.create(
            organization=organization, name="Monthly", frequency="monthly", periods_per_year=12
        )
        period = PayrollPeriod.objects.create(
            organization=organization,
            schedule=schedule,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            pay_date=date(2026, 1, 31),
        )
        with self.assertRaises(UnsupportedJurisdictionError):
            process_payroll(period=period, idempotency_key="must-not-calculate")

    def test_filing_liability_payment_amendment_and_exports(self):
        rule = self.import_and_activate()
        organization = Organization.objects.create(name="Acme", slug="acme-tax")
        OrganizationTaxConfiguration.objects.create(organization=organization, jurisdiction=self.jurisdiction)
        period = FilingPeriod.objects.create(
            organization=organization,
            jurisdiction=self.jurisdiction,
            period_type="quarterly",
            starts_on=date(2026, 1, 1),
            ends_on=date(2026, 3, 31),
            due_on=date(2026, 4, 30),
        )
        TaxLiability.objects.create(
            organization=organization,
            filing_period=period,
            rule_version=rule,
            liability_type="withholding",
            amount="123.45",
            payment_reference="PAY-1",
            source_calculation_ids=[1, 2],
        )
        amendment = FilingAmendment.objects.create(
            organization=organization,
            filing_period=period,
            sequence=1,
            reason="Retroactive adjustment",
            replaces_reference="PAY-1",
            changes={"amount": "5.00"},
        )
        export = create_filing_export(period, "json", amendment=amendment)
        self.assertIn("PAY-1", export.payload)
        with self.assertRaises(ValidationError):
            create_filing_export(period, "xml")
