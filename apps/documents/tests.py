from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.auditing.models import AuditAction, AuditEvent
from apps.organizations.models import Organization, OrganizationMembership, OrganizationRole

from .models import AccessClassification, Document
from .services.uploads import create_attachment, validate_and_scan
from .services.workflows import place_legal_hold, purge_expired_document


class SecureDocumentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", email="owner@example.com", password="test")
        self.organization = Organization.objects.create(name="Example", slug="example")
        OrganizationMembership.objects.create(
            user=self.user, organization=self.organization, role=OrganizationRole.ADMINISTRATOR
        )
        self.document = Document.objects.create(
            organization=self.organization,
            owner=self.user,
            title="Payroll statement",
            category="financial",
            access_classification=AccessClassification.HIGHLY_SENSITIVE,
            retention_until=timezone.localdate() - timedelta(days=1),
        )

    def test_upload_is_scanned_hashed_and_given_private_nonguessable_key(self):
        upload = SimpleUploadedFile("statement.pdf", b"%PDF-1.4 safe", content_type="application/pdf")
        attachment = create_attachment(document=self.document, upload=upload, actor=self.user)
        self.assertEqual(attachment.malware_scan_status, "clean")
        self.assertEqual(len(attachment.checksum_sha256), 64)
        self.assertNotIn("statement", attachment.file.name)
        self.assertTrue(AuditEvent.objects.filter(action=AuditAction.CREATE, object_id=attachment.pk).exists())

    def test_malware_signature_and_spoofed_type_are_rejected(self):
        malware = SimpleUploadedFile("unsafe.txt", b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR", content_type="text/plain")
        with self.assertRaises(ValidationError):
            validate_and_scan(malware)
        spoofed = SimpleUploadedFile("unsafe.pdf", b"not a pdf", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_and_scan(spoofed)

    def test_legal_hold_blocks_retention_purge(self):
        place_legal_hold(document=self.document, actor=self.user, reason="Litigation")
        with self.assertRaisesMessage(ValidationError, "legal hold"):
            purge_expired_document(document=self.document, actor=self.user)
