"""Small dependency-free factories for cross-domain integration tests.

Factories deliberately require the tenant relationship to be explicit. This keeps
security tests readable and prevents fixtures from accidentally hiding a
cross-tenant reference.
"""

from datetime import date
from decimal import Decimal
from itertools import count

from apps.accounts.models import User
from apps.auditing.models import AuditAction, AuditEvent
from apps.clients.models import Client
from apps.documents.models import AccessClassification, Document, DocumentCategory
from apps.employees.models import Employee
from apps.finance.models import AccountCategory, FinancialAccount, LedgerEntry
from apps.organizations.models import Organization, OrganizationMembership, OrganizationRole
from apps.payroll.models import EmployeePayrollInput, InputType, PayrollPeriod, PaySchedule
from apps.risk.models import RiskImpact, RiskLikelihood, RiskRegisterEntry
from apps.taxation.models import Jurisdiction

_sequence = count(1)


def _next():
    return next(_sequence)


def user(**overrides):
    number = _next()
    values = {"username": f"user-{number}", "email": f"user-{number}@example.test", "password": "test-password"}
    values.update(overrides)
    password = values.pop("password")
    return User.objects.create_user(password=password, **values)


def organization(**overrides):
    number = _next()
    values = {"name": f"Organization {number}", "slug": f"organization-{number}"}
    values.update(overrides)
    return Organization.objects.create(**values)


def membership(*, member=None, tenant=None, role=OrganizationRole.ADMINISTRATOR, **overrides):
    values = {"user": member or user(), "organization": tenant or organization(), "role": role}
    values.update(overrides)
    return OrganizationMembership.objects.create(**values)


def employee(*, tenant=None, **overrides):
    number = _next()
    values = {
        "organization": tenant or organization(),
        "employee_number": f"E-{number}",
        "given_name": "Ada",
        "family_name": "Lovelace",
        "hire_date": date(2025, 1, 1),
    }
    values.update(overrides)
    return Employee.objects.create(**values)


def client(*, tenant=None, **overrides):
    number = _next()
    values = {
        "organization": tenant or organization(),
        "code": f"C-{number}",
        "display_name": f"Client {number}",
        "legal_name": f"Client {number} LLC",
        "jurisdiction": "US",
    }
    values.update(overrides)
    return Client.objects.create(**values)


def payroll_period(*, tenant=None, **overrides):
    tenant = tenant or organization()
    schedule = overrides.pop("schedule", None) or PaySchedule.objects.create(
        organization=tenant, name=f"Monthly {_next()}", frequency="monthly", periods_per_year=12
    )
    values = {
        "organization": tenant,
        "schedule": schedule,
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 1, 31),
        "pay_date": date(2026, 2, 1),
    }
    values.update(overrides)
    return PayrollPeriod.objects.create(**values)


def payroll_input(*, period=None, worker=None, **overrides):
    period = period or payroll_period()
    worker = worker or employee(tenant=period.organization)
    values = {
        "organization": period.organization,
        "period": period,
        "employee": worker,
        "input_type": InputType.BASE_SALARY,
        "description": "Monthly salary",
        "amount": Decimal("1000.00"),
        "source_key": f"salary-{_next()}",
        "metadata": {"worked_days": 31, "period_days": 31},
    }
    values.update(overrides)
    return EmployeePayrollInput.objects.create(**values)


def jurisdiction(**overrides):
    number = _next()
    values = {
        "code": f"US-T{number}",
        "name": f"Test jurisdiction {number}",
        "country_code": "US",
        "supported": True,
        "calculator_key": "table",
        "filing_export_formats": ["json"],
    }
    values.update(overrides)
    return Jurisdiction.objects.create(**values)


def ledger_entry(*, tenant=None, category=AccountCategory.REVENUE, amount=Decimal("100.00"), **overrides):
    tenant = tenant or organization()
    number = _next()
    account = overrides.pop("account", None) or FinancialAccount.objects.create(
        organization=tenant, code=f"A-{number}", name=f"Account {number}", category=category
    )
    values = {
        "organization": tenant,
        "account": account,
        "entry_date": date(2026, 1, 31),
        "amount": amount,
        "description": "Factory ledger entry",
        "source_type": "test",
        "source_reference": f"source-{number}",
    }
    values.update(overrides)
    return LedgerEntry.objects.create(**values)


def document(*, tenant=None, owner=None, **overrides):
    tenant = tenant or organization()
    owner = owner or user()
    if not owner.organization_memberships.filter(organization=tenant).exists():
        membership(member=owner, tenant=tenant)
    values = {
        "organization": tenant,
        "owner": owner,
        "title": f"Document {_next()}",
        "category": DocumentCategory.PAYROLL,
        "access_classification": AccessClassification.HIGHLY_SENSITIVE,
    }
    values.update(overrides)
    return Document.objects.create(**values)


def audit_event(*, tenant=None, actor=None, **overrides):
    tenant = tenant or organization()
    values = {
        "organization": tenant,
        "actor": actor,
        "action": AuditAction.ACCESS,
        "object_type": "tests.FactoryObject",
        "object_id": str(_next()),
    }
    values.update(overrides)
    return AuditEvent.objects.create(**values)


def analytics_context(*, tenant=None, actor=None):
    tenant = tenant or organization()
    actor = actor or user()
    membership(member=actor, tenant=tenant)
    return tenant, actor, ledger_entry(tenant=tenant)


def risk_entry(*, tenant=None, owner=None, **overrides):
    tenant = tenant or organization()
    owner = owner or user()
    if not owner.organization_memberships.filter(organization=tenant).exists():
        membership(member=owner, tenant=tenant)
    values = {
        "organization": tenant,
        "title": f"Risk {_next()}",
        "description": "Factory risk",
        "likelihood": RiskLikelihood.POSSIBLE,
        "impact": RiskImpact.MODERATE,
        "owner": owner,
        "mitigation": "Test controls",
        "review_date": date(2026, 12, 31),
    }
    values.update(overrides)
    return RiskRegisterEntry.objects.create(**values)
