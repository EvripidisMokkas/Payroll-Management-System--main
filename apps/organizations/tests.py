from django.test import SimpleTestCase
from django.urls import reverse


class DomainStatusTests(SimpleTestCase):
    def test_status_endpoint(self):
        response = self.client.get(reverse("organizations:status"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["domain"], "organizations")
