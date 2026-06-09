from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.organizations.models import Organization, OrganizationMembership, OrganizationRole

from .models import AccountCategory, FinancialAccount, InsurancePolicy, LedgerEntry, MetricType, Product
from .services.calculations import calculate_metrics
from .services.forecasting import create_prediction


class FinanceDomainTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme", slug="acme")
        self.user = User.objects.create_user(username="admin", email="admin@example.com", password="password")
        OrganizationMembership.objects.create(
            user=self.user, organization=self.organization, role=OrganizationRole.ADMINISTRATOR
        )
        self.revenue = FinancialAccount.objects.create(
            organization=self.organization, code="4000", name="Revenue", category=AccountCategory.REVENUE
        )
        self.payroll = FinancialAccount.objects.create(
            organization=self.organization, code="6000", name="Payroll", category=AccountCategory.PAYROLL_COST
        )
        for account, amount, reference in ((self.revenue, "1000", "sale-1"), (self.payroll, "250", "run-1")):
            LedgerEntry.objects.create(
                organization=self.organization,
                account=account,
                entry_date=date(2026, 1, 31),
                amount=amount,
                description=reference,
                source_type="test",
                source_reference=reference,
            )

    def test_calculation_service_returns_financial_metrics(self):
        metrics = calculate_metrics(self.organization, date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(metrics[MetricType.GROSS_PROFIT], Decimal("1000"))
        self.assertEqual(metrics[MetricType.OPERATING_PROFIT], Decimal("750"))
        self.assertEqual(metrics[MetricType.PAYROLL_REVENUE_RATIO], Decimal("25"))

    def test_prediction_records_provenance_confidence_and_disclaimer(self):
        run = create_prediction(
            organization=self.organization,
            metric_type=MetricType.GROSS_PROFIT,
            observations=[(date(2026, 1, 1), 100), (date(2026, 2, 1), 120)],
            horizon=2,
            assumptions={"growth": "linear"},
            created_by=self.user,
        )
        self.assertEqual(run.model_version, "linear-trend-v1")
        self.assertIn("not guaranteed", run.disclaimer)
        self.assertEqual(run.points.count(), 2)
        self.assertLessEqual(run.points.first().confidence_low, run.points.first().predicted_value)

    def test_source_records_are_tenant_and_role_scoped(self):
        employee = User.objects.create_user(username="employee", email="employee@example.com", password="password")
        OrganizationMembership.objects.create(
            user=employee, organization=self.organization, role=OrganizationRole.EMPLOYEE
        )
        self.client.force_login(employee)
        response = self.client.get(reverse("finance:ledger-sources", args=[self.organization.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["records"], [])

    def test_cross_organization_insurance_relation_is_rejected(self):
        other = Organization.objects.create(name="Other", slug="other")
        product = Product.objects.create(organization=other, code="POL", name="Policy")
        policy = InsurancePolicy(
            organization=self.organization,
            product=product,
            policy_number="P-1",
            coverage_limit=1000,
            effective_from=date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            policy.full_clean()
