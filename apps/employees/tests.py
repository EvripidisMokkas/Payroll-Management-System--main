from datetime import date

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.organizations.models import Organization

from .models import Employee, EmploymentStatus, Salary


class DomainStatusTests(SimpleTestCase):
    def test_status_endpoint(self):
        response = self.client.get(reverse("employees:status"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["domain"], "employees")


class EmployeeModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Acme", legal_name="Acme LLC", slug="acme", registration_number="ACME-1", jurisdiction="US"
        )
        self.employee = Employee.objects.create(
            organization=self.organization,
            employee_number="E-1",
            given_name="Ada",
            family_name="Lovelace",
            hire_date=date(2025, 1, 1),
        )

    def test_rejects_invalid_status_transition(self):
        self.employee.status = EmploymentStatus.TERMINATED
        self.employee.termination_date = date(2025, 2, 1)
        with self.assertRaises(ValidationError):
            self.employee.full_clean()

    def test_rejects_overlapping_salary_period(self):
        Salary.objects.create(
            organization=self.organization,
            employee=self.employee,
            amount="1000.00",
            currency="USD",
            frequency="monthly",
            effective_from=date(2025, 1, 1),
            effective_to=date(2025, 6, 30),
        )
        overlapping = Salary(
            organization=self.organization,
            employee=self.employee,
            amount="1200.00",
            currency="USD",
            frequency="monthly",
            effective_from=date(2025, 6, 1),
        )
        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_rejects_unsupported_currency(self):
        salary = Salary(
            organization=self.organization,
            employee=self.employee,
            amount="1000.00",
            currency="usd",
            frequency="monthly",
            effective_from=date(2025, 1, 1),
        )
        with self.assertRaises(ValidationError):
            salary.full_clean()


class PrivacyWorkflowTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User
        from apps.employees.services.privacy import approve_request, create_request
        from apps.organizations.models import Organization

        self.organization = Organization.objects.create(name="Privacy Org", slug="privacy-org")
        self.employee = Employee.objects.create(
            organization=self.organization,
            employee_number="P-1",
            given_name="Grace",
            family_name="Hopper",
            work_email="grace@example.com",
            hire_date=date(2025, 1, 1),
        )
        self.requester = User.objects.create_user(
            username="requester", email="requester@example.com", password="long-safe-password"
        )
        self.approver = User.objects.create_superuser(
            username="approver", email="approver@example.com", password="long-safe-password"
        )
        self.create_request = create_request
        self.approve_request = approve_request

    def approved_request(self, request_type):
        record = self.create_request(employee=self.employee, request_type=request_type, requested_by=self.requester)
        return self.approve_request(
            request_record=record,
            approved_by=self.approver,
            legal_basis="Verified request; statutory payroll retention applies.",
        )

    def test_export_is_audited_and_contains_preservation_notice(self):
        from apps.employees.models import PrivacyRequestType
        from apps.employees.services.privacy import export_employee_data

        content = export_employee_data(
            request_record=self.approved_request(PrivacyRequestType.EXPORT), actor=self.approver
        )
        self.assertIn(b"preservation_notice", content)
        self.assertIn(b"grace@example.com", content)

    def test_deletion_minimizes_contact_data_but_preserves_employee(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.employees.models import EmployeePersonalInformation, PrivacyRequestType
        from apps.employees.services.privacy import delete_employee_data

        EmployeePersonalInformation.objects.create(
            organization=self.organization, employee=self.employee, legal_name_encrypted="Grace Brewster Hopper"
        )
        delete_employee_data(
            request_record=self.approved_request(PrivacyRequestType.DELETION),
            actor=self.approver,
            retention_until=timezone.localdate() + timedelta(days=365),
        )
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.work_email, "")
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())
        self.assertEqual(self.employee.personal_information.legal_name_encrypted, "")
