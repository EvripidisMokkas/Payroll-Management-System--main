"""Create a representative browser workspace for local inspection."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.auditing.models import AuditAction, AuditEvent
from apps.clients.models import Client
from apps.documents.models import AccessClassification, Document, DocumentCategory
from apps.employees.models import Employee, EmploymentStatus
from apps.finance.models import AccountCategory, FinancialAccount
from apps.organizations.models import (
    LifecycleStatus,
    Organization,
    OrganizationMembership,
    OrganizationRole,
)
from apps.payroll.models import PaySchedule, PayrollLifecycle, PayrollPeriod
from apps.risk.models import RiskImpact, RiskLikelihood, RiskRegisterEntry, RiskStatus


class Command(BaseCommand):
    help = "Seed a local organization, operational records, and one user for every RBAC role."

    def handle(self, *args, **options):
        organization, _ = Organization.objects.update_or_create(
            slug="northstar-demo",
            defaults={
                "name": "Northstar Payroll Group",
                "legal_name": "Northstar Payroll Group LLC",
                "jurisdiction": "US",
                "billing_email": "finance@northstar.example",
                "default_currency": "USD",
                "status": LifecycleStatus.ACTIVE,
                "is_active": True,
            },
        )
        users = {}
        User = get_user_model()
        for role in OrganizationRole.values:
            username = role.replace("_", "-")
            user, _ = User.objects.get_or_create(username=username, defaults={"email": f"{username}@northstar.example"})
            user.set_password("Demo123!Pass")
            user.save()
            OrganizationMembership.objects.update_or_create(
                user=user, organization=organization, defaults={"role": role, "is_active": True}
            )
            users[role] = user

        for number, given_name, family_name, status in (
            ("EMP-001", "Maya", "Brooks", EmploymentStatus.ACTIVE),
            ("EMP-002", "Theo", "Martinez", EmploymentStatus.ACTIVE),
            ("EMP-003", "Ari", "Chen", EmploymentStatus.LEAVE),
        ):
            Employee.objects.update_or_create(
                organization=organization,
                employee_number=number,
                defaults={
                    "given_name": given_name,
                    "family_name": family_name,
                    "work_email": f"{given_name.lower()}@northstar.example",
                    "hire_date": date.today() - timedelta(days=500),
                    "status": status,
                },
            )

        Client.objects.update_or_create(
            organization=organization,
            code="CL-100",
            defaults={
                "display_name": "Brightline Studio",
                "legal_name": "Brightline Studio Inc.",
                "registration_number": "BRIGHT-100",
                "jurisdiction": "US",
                "status": LifecycleStatus.ACTIVE,
            },
        )
        schedule, _ = PaySchedule.objects.update_or_create(
            organization=organization,
            name="Biweekly Payroll",
            defaults={"frequency": "biweekly", "periods_per_year": 26, "currency": "USD", "active": True},
        )
        PayrollPeriod.objects.update_or_create(
            organization=organization,
            schedule=schedule,
            period_start=date.today() - timedelta(days=14),
            defaults={
                "period_end": date.today() - timedelta(days=1),
                "pay_date": date.today() + timedelta(days=3),
                "status": PayrollLifecycle.APPROVAL,
            },
        )
        FinancialAccount.objects.update_or_create(
            organization=organization,
            code="PAY-100",
            defaults={
                "name": "Payroll expense",
                "category": AccountCategory.PAYROLL_COST,
                "currency": "USD",
                "is_active": True,
            },
        )
        Document.objects.update_or_create(
            organization=organization,
            title="June payroll control checklist",
            defaults={
                "owner": users[OrganizationRole.PAYROLL_OPERATOR],
                "category": DocumentCategory.PAYROLL,
                "access_classification": AccessClassification.CONFIDENTIAL,
                "metadata": {"demo": True},
            },
        )
        RiskRegisterEntry.objects.update_or_create(
            organization=organization,
            title="Late payroll approval",
            defaults={
                "description": "Payroll approval may miss the banking submission deadline.",
                "likelihood": RiskLikelihood.POSSIBLE,
                "impact": RiskImpact.MAJOR,
                "owner": users[OrganizationRole.ADMINISTRATOR],
                "mitigation": "Require approval 48 hours before payment submission.",
                "review_date": date.today() + timedelta(days=30),
                "status": RiskStatus.MITIGATING,
            },
        )
        if not AuditEvent.objects.filter(organization=organization, object_id="browser-demo").exists():
            AuditEvent.objects.create(
                organization=organization,
                actor=users[OrganizationRole.ADMINISTRATOR],
                action=AuditAction.CREATE,
                object_type="browser_workspace",
                object_id="browser-demo",
                object_label="Browser demo environment",
                after_summary={"status": "ready"},
            )

        self.stdout.write(self.style.SUCCESS("Browser demo ready. Password for all role users: Demo123!Pass"))
