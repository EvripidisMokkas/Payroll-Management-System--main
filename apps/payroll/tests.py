from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.employees.models import Employee
from apps.organizations.models import Organization, OrganizationMembership, OrganizationRole
from apps.payroll.models import (
    CalculationRun,
    EmployeePayrollInput,
    InputType,
    PayrollLifecycle,
    PayrollLineItem,
    PayrollPeriod,
    PaySchedule,
)
from apps.payroll.services import create_adjustment_run, process_payroll, transition_period
from apps.payroll.services.v1 import calculate, money


class DomainStatusTests(SimpleTestCase):
    def test_status_endpoint(self):
        response = self.client.get(reverse("payroll:status"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["domain"], "payroll")


class VersionOneCalculationTests(SimpleTestCase):
    def test_money_rounds_half_up(self):
        self.assertEqual(money("10.125"), Decimal("10.13"))
        self.assertEqual(money("10.124"), Decimal("10.12"))

    def test_partial_period_and_every_supported_component(self):
        inputs = [
            self.input(InputType.BASE_SALARY, amount="3000", metadata={"worked_days": 10, "period_days": 20}),
            self.input(InputType.HOURLY, rate="20", quantity="2.5"),
            self.input(InputType.OVERTIME, rate="20", quantity="2", metadata={"multiplier": "1.5"}),
            self.input(InputType.BONUS, amount="100"),
            self.input(InputType.COMMISSION, amount="75"),
            self.input(InputType.BENEFIT, amount="25"),
            self.input(InputType.PRE_TAX_DEDUCTION, amount="50"),
            self.input(InputType.POST_TAX_DEDUCTION, amount="20"),
            self.input(InputType.EMPLOYER_COST, amount="45"),
        ]
        result = calculate(inputs)
        self.assertEqual(result["gross_pay"], Decimal("1810.00"))
        self.assertEqual(result["pre_tax_deductions"], Decimal("50.00"))
        self.assertEqual(result["post_tax_deductions"], Decimal("20.00"))
        self.assertEqual(result["employer_costs"], Decimal("45.00"))
        self.assertEqual(result["net_pay"], Decimal("1740.00"))

    def test_negative_adjustment_reduces_pay(self):
        result = calculate([self.input(InputType.BONUS, amount="-25")])
        self.assertEqual(result["gross_pay"], Decimal("-25.00"))
        self.assertEqual(result["net_pay"], Decimal("-25.00"))

    @staticmethod
    def input(input_type, *, amount="0", quantity="1", rate="0", metadata=None):
        return {
            "employee_id": 1,
            "input_type": input_type,
            "description": "test",
            "amount": amount,
            "quantity": quantity,
            "rate": rate,
            "metadata": metadata or {},
        }


class PayrollProcessingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="Acme", slug="acme")
        cls.schedule = PaySchedule.objects.create(
            organization=cls.organization, name="Monthly", frequency="monthly", periods_per_year=12
        )
        cls.period = PayrollPeriod.objects.create(
            organization=cls.organization,
            schedule=cls.schedule,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            pay_date=date(2026, 2, 1),
        )
        cls.employee = Employee.objects.create(
            organization=cls.organization,
            employee_number="E-1",
            given_name="Ada",
            family_name="Lovelace",
            hire_date=date(2025, 1, 1),
        )
        cls.operator = User.objects.create_user(username="operator", email="operator@example.com")
        cls.admin = User.objects.create_user(username="admin", email="admin@example.com")
        cls.auditor = User.objects.create_user(username="auditor", email="auditor@example.com")
        OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.operator, role=OrganizationRole.PAYROLL_OPERATOR
        )
        OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.admin, role=OrganizationRole.ADMINISTRATOR
        )
        OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.auditor, role=OrganizationRole.AUDITOR
        )

    def create_input(self, **overrides):
        values = {
            "organization": self.organization,
            "period": self.period,
            "employee": self.employee,
            "input_type": InputType.BASE_SALARY,
            "description": "Monthly salary",
            "amount": Decimal("1000"),
            "source_key": "salary-1",
            "metadata": {"worked_days": 31, "period_days": 31},
        }
        values.update(overrides)
        return EmployeePayrollInput.objects.create(**values)

    def test_regular_inputs_reject_negative_values(self):
        with self.assertRaises(ValidationError):
            self.create_input(amount=Decimal("-1"))

    def test_processing_is_idempotent_and_keeps_reproducible_snapshot(self):
        payroll_input = self.create_input()
        first = process_payroll(period=self.period, idempotency_key="jan-v1", actor=self.operator)
        payroll_input.amount = Decimal("1200")
        payroll_input.save()
        second = process_payroll(period=self.period, idempotency_key="jan-v1", actor=self.operator)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CalculationRun.objects.count(), 1)
        self.assertEqual(first.input_snapshot[0]["amount"], "1000.0000")
        self.assertEqual(first.rules_snapshot["version"], "v1")
        self.assertEqual(first.tax_jurisdiction_code, "not_applicable")
        self.assertEqual(first.tax_rule_version, "not_applicable")
        self.assertTrue(first.explanation)
        self.assertTrue(PayrollLineItem.objects.get(run=first).explanation)

    def test_retroactive_change_requires_adjustment_and_preserves_original(self):
        self.create_input()
        original = process_payroll(period=self.period, idempotency_key="original", actor=self.operator)
        PayrollPeriod.objects.filter(pk=self.period.pk).update(status=PayrollLifecycle.PAID)
        self.period.refresh_from_db()

        adjustment = create_adjustment_run(
            original_period=self.period,
            inputs=[
                {
                    "employee_id": self.employee.pk,
                    "input_type": InputType.BONUS,
                    "amount": "-100",
                    "description": "Retroactive bonus reversal",
                }
            ],
            reason="Bonus entered in error",
            idempotency_key="correction-1",
            actor=self.admin,
        )
        self.assertEqual(original.net_pay, Decimal("1000.00"))
        self.assertEqual(adjustment.adjustment_of, original)
        self.assertEqual(adjustment.net_pay, Decimal("-100.00"))
        self.assertEqual(adjustment.correction.reason, "Bonus entered in error")

    def test_approval_roles_and_locked_period_enforcement(self):
        payroll_input = self.create_input()
        process_payroll(period=self.period, idempotency_key="approval", actor=self.operator)
        period = transition_period(period=self.period, to_status=PayrollLifecycle.VALIDATION, actor=self.operator)

        with self.assertRaises(PermissionDenied):
            transition_period(period=period, to_status=PayrollLifecycle.APPROVAL, actor=self.operator)
        with self.assertRaises(PermissionDenied):
            transition_period(period=period, to_status=PayrollLifecycle.APPROVAL, actor=self.auditor)

        period = transition_period(period=period, to_status=PayrollLifecycle.APPROVAL, actor=self.admin)
        period = transition_period(period=period, to_status=PayrollLifecycle.LOCKED, actor=self.admin)
        payroll_input.amount = Decimal("900")
        with self.assertRaises(ValidationError):
            payroll_input.save()
        with self.assertRaises(ValidationError):
            process_payroll(period=period, idempotency_key="late", actor=self.operator)

    def test_calculation_snapshots_are_immutable(self):
        self.create_input()
        run = process_payroll(period=self.period, idempotency_key="immutable", actor=self.operator)
        run.net_pay = Decimal("0")
        with self.assertRaises(ValidationError):
            run.save()
        with self.assertRaises(ValidationError):
            run.delete()
