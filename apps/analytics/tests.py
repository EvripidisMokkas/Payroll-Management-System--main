from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.organizations.models import Organization, OrganizationMembership, OrganizationRole


class AnalyticsDashboardTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme", slug="acme")

    def membership(self, role):
        user = User.objects.create_user(username=role, email=f"{role}@example.com", password="password")
        OrganizationMembership.objects.create(user=user, organization=self.organization, role=role)
        self.client.force_login(user)
        return user

    def test_administrator_dashboard_has_scoped_inspectable_charts_and_warning(self):
        self.membership(OrganizationRole.ADMINISTRATOR)
        response = self.client.get(reverse("analytics:dashboard-api", args=[self.organization.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["charts"])
        self.assertIn("ledger-sources", response.json()["charts"][0]["source_url"])
        self.assertEqual(response.json()["warnings"][0]["code"], "NO_SOURCE_DATA")

    def test_employee_dashboard_hides_organization_financial_charts(self):
        self.membership(OrganizationRole.EMPLOYEE)
        response = self.client.get(reverse("analytics:dashboard-api", args=[self.organization.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["charts"], [])

    def test_non_member_cannot_view_dashboard(self):
        user = User.objects.create_user(username="outsider", email="outsider@example.com", password="password")
        self.client.force_login(user)
        response = self.client.get(reverse("analytics:dashboard-api", args=[self.organization.id]))
        self.assertEqual(response.status_code, 403)
