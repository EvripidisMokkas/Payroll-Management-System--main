from datetime import date

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.organizations.models import Organization

from .models import Client, ServiceAgreement


class DomainStatusTests(SimpleTestCase):
    def test_status_endpoint(self):
        response = self.client.get(reverse("clients:status"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["domain"], "clients")


class ClientModelTests(TestCase):
    def test_rejects_agreement_end_before_start(self):
        organization = Organization.objects.create(name="Acme", slug="acme", registration_number="ACME-1")
        client = Client.objects.create(
            organization=organization, code="C-1", display_name="Client", legal_name="Client LLC", jurisdiction="US"
        )
        agreement = ServiceAgreement(
            organization=organization,
            client=client,
            agreement_number="A-1",
            fee_amount="100.00",
            currency="USD",
            effective_from=date(2025, 2, 1),
            effective_to=date(2025, 1, 1),
        )
        with self.assertRaises(ValidationError):
            agreement.full_clean()
