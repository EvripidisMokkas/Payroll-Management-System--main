import base64

from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import Organization, OrganizationMembership, OrganizationRole
from apps.organizations.services import assign_membership, authorize
from apps.payroll.models import PayrollRecord

from .mfa import verify_totp
from .models import User
from .roles import ROLE_PERMISSIONS


class AuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="A", slug="a")
        cls.org_b = Organization.objects.create(name="B", slug="b")
        cls.users = {}
        for role, _ in OrganizationRole.choices:
            user = User.objects.create_user(username=role, email=f"{role}@example.com", password="safe-password")
            OrganizationMembership.objects.create(user=user, organization=cls.org_a, role=role)
            cls.users[role] = user
        cls.outsider = User.objects.create_user(
            username="outsider", email="outside@example.com", password="safe-password"
        )
        cls.other_employee = User.objects.create_user(
            username="other", email="other@example.com", password="safe-password"
        )
        OrganizationMembership.objects.create(
            user=cls.other_employee, organization=cls.org_b, role=OrganizationRole.EMPLOYEE
        )
        cls.own_record = PayrollRecord.objects.create(
            organization=cls.org_a, employee=cls.users[OrganizationRole.EMPLOYEE], employee_name="Own", gross_amount=100
        )
        cls.other_record = PayrollRecord.objects.create(
            organization=cls.org_a,
            employee=cls.users[OrganizationRole.ADMINISTRATOR],
            employee_name="Other",
            gross_amount=200,
        )
        cls.cross_record = PayrollRecord.objects.create(
            organization=cls.org_b, employee=cls.other_employee, employee_name="Cross", gross_amount=300
        )

    def test_role_groups_have_only_explicit_permissions(self):
        for role, expected in ROLE_PERMISSIONS.items():
            self.assertTrue(self.users[role].groups.filter(name=role).exists())
            self.assertEqual(
                set(Group.objects.get(name=role).permissions.values_list("codename", flat=True)), set(expected)
            )

    def test_administrator_can_assign_role_but_operator_cannot_escalate(self):
        membership = assign_membership(
            self.users[OrganizationRole.ADMINISTRATOR], self.outsider, self.org_a, OrganizationRole.CLIENT
        )
        self.assertEqual(membership.role, OrganizationRole.CLIENT)
        with self.assertRaises(PermissionDenied):
            assign_membership(
                self.users[OrganizationRole.PAYROLL_OPERATOR], self.outsider, self.org_a, OrganizationRole.ADMINISTRATOR
            )

    def test_role_action_matrix_and_auditor_read_only_exception(self):
        authorize(self.users[OrganizationRole.ADMINISTRATOR], self.org_a, "payroll.delete")
        authorize(self.users[OrganizationRole.PAYROLL_OPERATOR], self.org_a, "payroll.write")
        authorize(self.users[OrganizationRole.EMPLOYEE], self.org_a, "payroll.read_own")
        authorize(self.users[OrganizationRole.AUDITOR], self.org_a, "audit.annotate")
        authorize(self.users[OrganizationRole.CLIENT], self.org_a, "audit.read")
        for action in ("payroll.write", "payroll.delete", "organization.manage"):
            with self.assertRaises(PermissionDenied):
                authorize(self.users[OrganizationRole.AUDITOR], self.org_a, action)

    def test_scoped_queryset_denies_cross_client_data(self):
        self.assertEqual(
            list(PayrollRecord.objects.for_user(self.users[OrganizationRole.CLIENT])),
            [self.own_record, self.other_record],
        )
        self.assertFalse(PayrollRecord.objects.for_user(self.outsider).exists())

    def test_employee_endpoint_has_object_level_own_record_access_only(self):
        self.client.force_login(self.users[OrganizationRole.EMPLOYEE])
        response = self.client.get(reverse("payroll:records", args=[self.org_a.pk]))
        self.assertEqual([item["id"] for item in response.json()["results"]], [self.own_record.pk])

    def test_all_roles_denied_cross_tenant_endpoint(self):
        for user in self.users.values():
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("payroll:records", args=[self.org_b.pk])).status_code, 403)

    def test_only_write_roles_can_create_payroll(self):
        url = reverse("payroll:records", args=[self.org_a.pk])
        payload = {"employee_name": "New", "gross_amount": "50.00", "status": "draft"}
        for role in (OrganizationRole.ADMINISTRATOR, OrganizationRole.PAYROLL_OPERATOR):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.post(url, payload).status_code, 201)
        for role in (OrganizationRole.EMPLOYEE, OrganizationRole.AUDITOR, OrganizationRole.CLIENT):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.post(url, payload).status_code, 403)

    def test_auditor_can_append_annotation_but_client_cannot(self):
        url = reverse("auditing:annotations", args=[self.org_a.pk])
        self.client.force_login(self.users[OrganizationRole.AUDITOR])
        self.assertEqual(self.client.post(url, {"note": "Reviewed"}).status_code, 201)
        self.client.force_login(self.users[OrganizationRole.CLIENT])
        self.assertEqual(self.client.post(url, {"note": "No"}).status_code, 403)


class AuthenticationSecurityTests(TestCase):
    @override_settings(ACCOUNT_LOCKOUT_THRESHOLD=2, ACCOUNT_LOCKOUT_DURATION=900)
    def test_account_locks_after_failed_logins(self):
        user = User.objects.create_user(username="locked", email="locked@example.com", password="correct")
        self.assertIsNone(authenticate(username="locked", password="wrong"))
        self.assertIsNone(authenticate(username="locked", password="wrong"))
        user.refresh_from_db()
        self.assertTrue(user.is_locked())
        self.assertIsNone(authenticate(username="locked", password="correct"))

    def test_known_totp_code_is_accepted(self):
        secret = base64.b32encode(b"12345678901234567890").decode()
        self.assertTrue(verify_totp(secret, "287082", now=59, window=0))

    def test_mfa_enabled_login_requires_token(self):
        User.objects.create_user(
            username="mfa",
            email="mfa@example.com",
            password="correct",
            mfa_enabled=True,
            mfa_secret=base64.b32encode(b"12345678901234567890").decode(),
        )
        response = self.client.post(reverse("accounts:login"), {"username": "mfa", "password": "correct"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "multi-factor")

    def test_password_reset_and_logout_routes_exist(self):
        self.assertEqual(self.client.get(reverse("accounts:password_reset")).status_code, 200)
        self.assertIn(self.client.post(reverse("accounts:logout")).status_code, (200, 302))


class FieldEncryptionTests(TestCase):
    def test_mfa_secret_is_encrypted_at_rest_and_decrypted_by_model(self):
        secret = base64.b32encode(b"12345678901234567890").decode()
        user = User.objects.create_user(
            username="encrypted", email="encrypted@example.com", password="long-safe-password", mfa_secret=secret
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT mfa_secret FROM accounts_user WHERE id = %s", [user.pk])
            stored = cursor.fetchone()[0]
        self.assertTrue(stored.startswith("enc:v1:"))
        user.refresh_from_db()
        self.assertEqual(user.mfa_secret, secret)


class HttpSecurityTests(TestCase):
    def test_security_headers_are_added(self):
        response = self.client.get(reverse("accounts:status"))
        self.assertEqual(response.headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    @override_settings(RATE_LIMIT_ENABLED=True, API_RATE_LIMIT=1, RATE_LIMIT_WINDOW_SECONDS=60)
    def test_rate_limit_rejects_excess_requests(self):
        self.assertEqual(self.client.get(reverse("accounts:status")).status_code, 200)
        response = self.client.get(reverse("accounts:status"))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "60")
