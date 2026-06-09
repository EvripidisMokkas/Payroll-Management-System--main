from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.employees.models import Employee, Salary
from apps.organizations.models import Organization, OrganizationMembership, OrganizationRole

from .models import CompensationCriterion, CompensationPolicy, RecommendationStatus, ScoringRule
from .services import apply_approved_recommendation, approve_recommendation, create_recommendation, policy_as_of


class DomainStatusTests(SimpleTestCase):
    def test_status_endpoint(self):
        response = self.client.get(reverse("compensation:status"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["domain"], "compensation")


class CompensationRecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="Acme", slug="acme")
        cls.employee = Employee.objects.create(
            organization=cls.organization,
            employee_number="E-1",
            given_name="Ada",
            family_name="Lovelace",
            hire_date=date(2020, 1, 1),
        )
        cls.salary = Salary.objects.create(
            organization=cls.organization,
            employee=cls.employee,
            amount=Decimal("100000.00"),
            currency="USD",
            frequency="annual",
            effective_from=date(2025, 1, 1),
        )
        cls.creator = User.objects.create_user(username="creator", email="creator@example.com")
        cls.approver = User.objects.create_user(username="approver", email="approver@example.com")
        cls.operator = User.objects.create_user(username="operator", email="operator@example.com")
        OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.creator, role=OrganizationRole.PAYROLL_OPERATOR
        )
        OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.approver, role=OrganizationRole.ADMINISTRATOR
        )
        OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.operator, role=OrganizationRole.PAYROLL_OPERATOR
        )

    def create_policy(self, **overrides):
        values = {
            "organization": self.organization,
            "name": "Annual review",
            "version": "v1",
            "currency": "USD",
            "effective_from": date(2026, 1, 1),
            "minimum_adjustment_percent": Decimal("0.0200"),
            "maximum_adjustment_percent": Decimal("0.1000"),
            "budget_limit": Decimal("50000.00"),
            "require_pay_equity_review": True,
        }
        values.update(overrides)
        return CompensationPolicy.objects.create(**values)

    def create_rule(self, policy, criterion, *, weight="1", minimum="0", maximum="100", **overrides):
        values = {
            "organization": self.organization,
            "policy": policy,
            "criterion": criterion,
            "weight": Decimal(weight),
            "threshold_min": Decimal(minimum),
            "threshold_max": Decimal(maximum),
            "target_value": Decimal(maximum),
            "effective_from": policy.effective_from,
        }
        values.update(overrides)
        return ScoringRule.objects.create(**values)

    def test_scoring_is_deterministic_and_snapshots_sources_and_policy(self):
        policy = self.create_policy()
        self.create_rule(policy, CompensationCriterion.SKILLS, weight="3")
        self.create_rule(policy, CompensationCriterion.PERFORMANCE, weight="2")
        source_a = {"skills": "80", "performance": "60", "pay_equity_deviation_percent": "0.01"}
        source_b = {"performance": "60", "pay_equity_deviation_percent": "0.01", "skills": "80"}

        first = create_recommendation(
            employee=self.employee,
            policy=policy,
            as_of_date=date(2026, 6, 1),
            source_data=source_a,
            actor=self.creator,
            pay_equity_reviewed=True,
        )
        second = create_recommendation(
            employee=self.employee,
            policy=policy,
            as_of_date=date(2026, 6, 1),
            source_data=source_b,
            actor=self.creator,
            pay_equity_reviewed=True,
        )

        self.assertEqual(first.score, Decimal("72.0000"))
        self.assertEqual(first.score, second.score)
        self.assertEqual(first.proposed_midpoint, second.proposed_midpoint)
        self.assertEqual(first.score_breakdown, second.score_breakdown)
        self.assertEqual(first.source_data_snapshot, second.source_data_snapshot)
        self.assertEqual(first.policy_snapshot["version"], "v1")
        self.assertIn("authorized human approves", first.explanation)
        self.salary.refresh_from_db()
        self.assertEqual(self.salary.amount, Decimal("100000.00"))

    def test_policy_and_scoring_rule_effective_dates_are_respected(self):
        old = self.create_policy(version="v1", effective_to=date(2026, 6, 30))
        new = self.create_policy(version="v2", effective_from=date(2026, 7, 1))
        self.assertEqual(
            policy_as_of(organization=self.organization, name="Annual review", as_of_date=date(2026, 6, 30)), old
        )
        self.assertEqual(
            policy_as_of(organization=self.organization, name="Annual review", as_of_date=date(2026, 7, 1)), new
        )

        self.create_rule(
            old,
            CompensationCriterion.SKILLS,
            weight="1",
            maximum="100",
            effective_to=date(2026, 3, 31),
        )
        self.create_rule(
            old,
            CompensationCriterion.SKILLS,
            weight="1",
            maximum="200",
            effective_from=date(2026, 4, 1),
        )
        march = create_recommendation(
            employee=self.employee,
            policy=old,
            as_of_date=date(2026, 3, 31),
            source_data={"skills": "100"},
            pay_equity_reviewed=True,
        )
        april = create_recommendation(
            employee=self.employee,
            policy=old,
            as_of_date=date(2026, 4, 1),
            source_data={"skills": "100"},
            pay_equity_reviewed=True,
        )
        self.assertEqual(march.score, Decimal("100.0000"))
        self.assertEqual(april.score, Decimal("50.0000"))
        self.assertNotEqual(march.policy_snapshot["rules"], april.policy_snapshot["rules"])

    def test_authorized_approval_is_required_before_salary_change(self):
        policy = self.create_policy()
        self.create_rule(policy, CompensationCriterion.PERFORMANCE)
        recommendation = create_recommendation(
            employee=self.employee,
            policy=policy,
            as_of_date=date(2026, 6, 1),
            source_data={"performance": "75"},
            actor=self.creator,
            pay_equity_reviewed=True,
        )

        with self.assertRaises(PermissionDenied):
            apply_approved_recommendation(
                recommendation=recommendation,
                actor=self.approver,
                effective_from=date(2026, 7, 1),
            )
        with self.assertRaises(PermissionDenied):
            approve_recommendation(recommendation=recommendation, actor=self.operator)
        self.assertEqual(Salary.objects.filter(employee=self.employee).count(), 1)

        approve_recommendation(recommendation=recommendation, actor=self.approver, explanation="Reviewed by HR")
        salary = apply_approved_recommendation(
            recommendation=recommendation,
            actor=self.approver,
            effective_from=date(2026, 7, 1),
            explanation="Applied after approval",
        )
        recommendation.refresh_from_db()
        self.salary.refresh_from_db()
        self.assertEqual(recommendation.status, RecommendationStatus.APPLIED)
        self.assertEqual(recommendation.resulting_salary, salary)
        self.assertEqual(recommendation.approvals.count(), 2)
        self.assertEqual(self.salary.effective_to, date(2026, 6, 30))

    def test_controls_block_prohibited_criteria_pay_equity_and_budget(self):
        policy = self.create_policy(prohibited_criteria=["age"], budget_limit=Decimal("100.00"))
        self.create_rule(policy, CompensationCriterion.PERFORMANCE)
        with self.assertRaises(ValidationError):
            create_recommendation(
                employee=self.employee,
                policy=policy,
                as_of_date=date(2026, 6, 1),
                source_data={"performance": "50", "age": "40"},
            )
        recommendation = create_recommendation(
            employee=self.employee,
            policy=policy,
            as_of_date=date(2026, 6, 1),
            source_data={"performance": "50", "pay_equity_deviation_percent": "0.20"},
            actor=self.creator,
            pay_equity_reviewed=False,
        )
        with self.assertRaises(ValidationError):
            approve_recommendation(recommendation=recommendation, actor=self.approver)
        self.assertFalse(recommendation.controls["budget_within_limit"])
        self.assertFalse(recommendation.controls["pay_equity_within_limit"])
