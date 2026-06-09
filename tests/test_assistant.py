"""Tests for the RBAC-aware operations assistant."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from apps.auditing.models import AuditAnnotation
from apps.organizations.models import Organization, OrganizationMembership, OrganizationRole
from apps.risk.models import RiskRegisterEntry
from payroll_platform.assistant import chat, execute_tool


class AssistantTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme Payroll", slug="acme-payroll")
        self.auditor = get_user_model().objects.create_user(
            username="auditor-test", email="auditor@example.com", password="StrongPass123!"
        )
        self.employee = get_user_model().objects.create_user(
            username="employee-test", email="employee@example.com", password="StrongPass123!"
        )
        OrganizationMembership.objects.create(
            user=self.auditor, organization=self.organization, role=OrganizationRole.AUDITOR
        )
        OrganizationMembership.objects.create(
            user=self.employee, organization=self.organization, role=OrganizationRole.EMPLOYEE
        )

    def test_unauthorized_write_tool_is_rejected_server_side(self):
        with self.assertRaises(PermissionDenied):
            execute_tool(self.employee, self.organization, "create_audit_note", {"note": "No access"})

    @patch("payroll_platform.assistant._ollama_chat")
    def test_write_tool_requires_signed_confirmation(self, ollama_chat):
        ollama_chat.return_value = {
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "create_audit_note", "arguments": {"note": "Reviewed controls"}}}
                ],
            }
        }

        proposal = chat(self.auditor, self.organization.pk, "Add an audit note")

        self.assertIn("confirmation", proposal)
        self.assertFalse(AuditAnnotation.objects.exists())
        completed = chat(
            self.auditor,
            self.organization.pk,
            "",
            confirmed_action=proposal["confirmation"],
        )
        self.assertIn("Operation completed", completed["reply"])
        self.assertTrue(AuditAnnotation.objects.filter(note="Reviewed controls").exists())

    def test_tampered_confirmation_is_rejected(self):
        with self.assertRaises(ValueError):
            chat(self.auditor, self.organization.pk, "", confirmed_action="tampered")

    def test_chat_endpoint_requires_organization_membership(self):
        other = Organization.objects.create(name="Other", slug="other")
        self.client.force_login(self.auditor)

        response = self.client.post(
            "/assistant/chat/",
            data={"organization_id": other.pk, "message": "Summarize"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_administrator_can_create_authorized_risk_entry(self):
        administrator = get_user_model().objects.create_user(
            username="admin-test", email="admin@example.com", password="StrongPass123!"
        )
        OrganizationMembership.objects.create(
            user=administrator, organization=self.organization, role=OrganizationRole.ADMINISTRATOR
        )

        result = execute_tool(
            administrator,
            self.organization,
            "create_risk_entry",
            {
                "title": "Late payroll inputs",
                "description": "Inputs may arrive after cutoff.",
                "likelihood": 3,
                "impact": 4,
                "mitigation": "Daily cutoff reminders.",
                "review_date": "2026-07-01",
            },
        )

        self.assertTrue(result["created"])
        self.assertTrue(RiskRegisterEntry.objects.filter(title="Late payroll inputs", owner=administrator).exists())
