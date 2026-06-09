from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.organizations.models import Organization

from .models import AuditAction, AuditEvent
from .services import export_audit_events, record_event


class AuditEventTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="auditor", email="auditor@example.com", password="test")
        self.organization = Organization.objects.create(name="Example", slug="example")

    def test_events_are_hash_chained_and_immutable(self):
        first = record_event(
            organization=self.organization,
            actor=self.user,
            action=AuditAction.CREATE,
            object_type="documents.Document",
            object_id="1",
            after={"title": "One"},
        )
        second = record_event(
            organization=self.organization,
            actor=self.user,
            action=AuditAction.UPDATE,
            object_type="documents.Document",
            object_id="1",
            before={"title": "One"},
            after={"title": "Two"},
        )
        self.assertEqual(second.previous_hash, first.integrity_hash)
        first.action = AuditAction.DELETE
        with self.assertRaisesMessage(ValidationError, "immutable"):
            first.save()
        with self.assertRaisesMessage(ValidationError, "immutable"):
            AuditEvent.objects.filter(pk=second.pk).delete()

    def test_filtered_exports_include_integrity_metadata(self):
        record_event(
            organization=self.organization,
            actor=self.user,
            action=AuditAction.ACCESS,
            object_type="documents.Document",
            object_id="1",
            sensitive=True,
        )
        queryset = AuditEvent.objects.filter(action=AuditAction.ACCESS)
        content, content_type, metadata = export_audit_events(queryset, "json")
        self.assertEqual(content_type, "application/json")
        self.assertEqual(metadata["record_count"], 1)
        self.assertIn(metadata["sha256"].encode(), content)
        pdf, pdf_type, _ = export_audit_events(queryset, "pdf")
        self.assertEqual(pdf_type, "application/pdf")
        self.assertTrue(pdf.startswith(b"%PDF"))
