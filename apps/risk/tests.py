from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.organizations.models import Organization, OrganizationMembership, OrganizationRole

from .models import RiskRegisterEntry


class RiskRegisterTests(TestCase):
    def test_score_and_owner_must_be_in_organization(self):
        organization = Organization.objects.create(name="Acme", slug="acme")
        outsider = User.objects.create_user(username="outsider", email="outsider@example.com", password="password")
        risk = RiskRegisterEntry(
            organization=organization,
            title="Revenue concentration",
            description="One client dominates revenue.",
            likelihood=4,
            impact=5,
            owner=outsider,
            mitigation="Diversify clients.",
            review_date=date(2026, 7, 1),
        )
        self.assertEqual(risk.score, 20)
        with self.assertRaises(ValidationError):
            risk.full_clean()
        OrganizationMembership.objects.create(
            user=outsider, organization=organization, role=OrganizationRole.ADMINISTRATOR
        )
        risk.full_clean()
