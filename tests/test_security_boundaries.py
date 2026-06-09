from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.documents.models import Attachment
from apps.documents.services.uploads import validate_and_scan
from apps.organizations.models import OrganizationRole
from apps.organizations.services import ROLE_ACTIONS, authorize
from tests import factories


class EndpointAuthorizationMatrixTests(TestCase):
    """Every tenant-scoped endpoint must fail closed before object handling."""

    def setUp(self):
        self.tenant = factories.organization()
        self.outsider = factories.user()
        self.document = factories.document(tenant=self.tenant)
        self.scoped_endpoints = [
            ("get", reverse("payroll:records", args=[self.tenant.pk])),
            ("post", reverse("payroll:records", args=[self.tenant.pk])),
            ("get", reverse("documents:list-create", args=[self.tenant.pk])),
            ("post", reverse("documents:list-create", args=[self.tenant.pk])),
            ("post", reverse("documents:upload", args=[self.tenant.pk, self.document.pk])),
            ("get", reverse("documents:download", args=[self.tenant.pk, self.document.pk, 999999])),
            ("get", reverse("finance:ledger-sources", args=[self.tenant.pk])),
            ("get", reverse("finance:predictions", args=[self.tenant.pk])),
            ("post", reverse("finance:predictions", args=[self.tenant.pk])),
            ("get", reverse("auditing:annotations", args=[self.tenant.pk])),
            ("post", reverse("auditing:annotations", args=[self.tenant.pk])),
            ("get", reverse("auditing:export", args=[self.tenant.pk])),
            ("get", reverse("analytics:dashboard-api", args=[self.tenant.pk])),
            ("get", reverse("analytics:dashboard", args=[self.tenant.pk])),
        ]

    def test_all_scoped_endpoints_reject_anonymous_requests(self):
        for method, url in self.scoped_endpoints:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data={})
                self.assertIn(response.status_code, (401, 403))

    def test_all_scoped_endpoints_reject_authenticated_non_members(self):
        self.client.force_login(self.outsider)
        for method, url in self.scoped_endpoints:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data={})
                self.assertEqual(response.status_code, 403)


class ServiceAuthorizationMatrixTests(TestCase):
    def test_every_service_action_rejects_permission_bypass_and_cross_tenant_actor(self):
        tenant = factories.organization()
        outsider = factories.user()
        all_actions = set().union(*ROLE_ACTIONS.values())

        for action in all_actions:
            with self.subTest(action=action), self.assertRaises(PermissionDenied):
                authorize(outsider, tenant, action)

    def test_each_role_is_denied_every_action_outside_its_explicit_allowlist(self):
        all_actions = set().union(*ROLE_ACTIONS.values()) | {"unknown.operation"}
        for role in OrganizationRole.values:
            tenant = factories.organization()
            actor = factories.user()
            factories.membership(member=actor, tenant=tenant, role=role)
            for action in all_actions - ROLE_ACTIONS[role]:
                with self.subTest(role=role, action=action), self.assertRaises(PermissionDenied):
                    authorize(actor, tenant, action)


class SecurityRegressionTests(TestCase):
    @override_settings(DOCUMENT_MAX_UPLOAD_BYTES=8)
    def test_oversized_and_active_content_uploads_are_rejected(self):
        oversized = SimpleUploadedFile("large.txt", b"123456789", content_type="text/plain")
        active = SimpleUploadedFile("payload.txt", b"<script>alert(1)</script>", content_type="text/plain")
        with self.assertRaises(ValidationError):
            validate_and_scan(oversized)
        with self.assertRaises(ValidationError):
            validate_and_scan(active)

    def test_cross_tenant_attachment_reference_is_rejected(self):
        first = factories.organization()
        second = factories.organization()
        actor = factories.user()
        factories.membership(member=actor, tenant=first)
        attachment = Attachment(
            organization=second,
            document=factories.document(tenant=first, owner=actor),
            file=SimpleUploadedFile("safe.txt", b"safe", content_type="text/plain"),
            original_filename="safe.txt",
            content_type="text/plain",
            size_bytes=4,
            checksum_sha256="0" * 64,
            uploaded_by=actor,
        )
        with self.assertRaises(ValidationError):
            attachment.full_clean()

    def test_payroll_api_rejects_cross_tenant_employee_reference(self):
        tenant = factories.organization()
        other = factories.organization()
        admin = factories.user()
        foreign_employee = factories.user()
        factories.membership(member=admin, tenant=tenant)
        factories.membership(member=foreign_employee, tenant=other, role=OrganizationRole.EMPLOYEE)
        self.client.force_login(admin)

        response = self.client.post(
            reverse("payroll:records", args=[tenant.pk]),
            {"employee": foreign_employee.pk, "employee_name": "Foreign", "gross_amount": "100.00"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("password", response.json())
        self.assertNotIn("email", response.json())

    def test_document_list_never_exposes_private_attachment_keys(self):
        tenant = factories.organization()
        actor = factories.user()
        factories.membership(member=actor, tenant=tenant)
        factories.document(tenant=tenant, owner=actor)
        self.client.force_login(actor)

        payload = self.client.get(reverse("documents:list-create", args=[tenant.pk])).json()
        serialized = str(payload).lower()
        self.assertNotIn("file", serialized)
        self.assertNotIn("checksum", serialized)
        self.assertNotIn("password", serialized)
