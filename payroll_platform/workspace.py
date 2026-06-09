"""Role-aware browser workspace configuration."""

from dataclasses import dataclass

from apps.auditing.models import AuditAnnotation, AuditEvent
from apps.clients.models import Client
from apps.compensation.models import CompensationRecommendation
from apps.documents.models import Document
from apps.employees.models import Employee
from apps.finance.models import FinancialAccount, FinancialMetric
from apps.organizations.models import OrganizationMembership
from apps.payroll.models import PayrollPeriod
from apps.risk.models import RiskRegisterEntry


@dataclass(frozen=True)
class WorkspaceDomain:
    slug: str
    label: str
    description: str
    icon: str
    model: type
    read_action: str
    write_action: str | None
    fields: tuple[str, ...]
    columns: tuple[str, ...]


DOMAINS = {
    domain.slug: domain
    for domain in (
        WorkspaceDomain(
            "employees", "People", "Employee profiles and workforce status", "◎", Employee,
            "employee.read", "employee.write",
            ("employee_number", "given_name", "family_name", "work_email", "work_phone", "hire_date", "status"),
            ("employee_number", "given_name", "family_name", "work_email", "status"),
        ),
        WorkspaceDomain(
            "clients", "Clients", "Client organizations and engagement status", "◇", Client,
            "client.read", "client.write",
            ("code", "display_name", "legal_name", "registration_number", "jurisdiction", "status"),
            ("code", "display_name", "legal_name", "jurisdiction", "status"),
        ),
        WorkspaceDomain(
            "payroll", "Payroll", "Pay periods, dates, and lifecycle status", "◷", PayrollPeriod,
            "payroll.read", "payroll.write",
            ("schedule", "period_start", "period_end", "pay_date", "status"),
            ("schedule", "period_start", "period_end", "pay_date", "status"),
        ),
        WorkspaceDomain(
            "documents", "Documents", "Secure records and retention controls", "▤", Document,
            "document.read", "document.write",
            ("title", "category", "access_classification", "retention_until"),
            ("title", "category", "access_classification", "retention_until", "created_at"),
        ),
        WorkspaceDomain(
            "finance", "Finance", "Financial accounts and reporting structure", "$", FinancialAccount,
            "finance.read", None,
            ("code", "name", "category", "currency", "is_active"),
            ("code", "name", "category", "currency", "is_active"),
        ),
        WorkspaceDomain(
            "audit", "Audit trail", "Immutable compliance and access evidence", "◫", AuditEvent,
            "audit.read", None, (),
            ("occurred_at", "action", "object_type", "object_label", "actor"),
        ),
        WorkspaceDomain(
            "audit-notes", "Audit notes", "Append-only auditor annotations", "+", AuditAnnotation,
            "audit.read", "audit.annotate",
            ("note",),
            ("created_at", "author", "note"),
        ),
        WorkspaceDomain(
            "compensation", "Compensation", "Pay recommendations and approval status", "%", CompensationRecommendation,
            "compensation.read", None, (),
            ("employee", "as_of_date", "status", "proposed_midpoint", "currency"),
        ),
        WorkspaceDomain(
            "analytics", "Analytics", "Calculated financial and payroll metrics", "=", FinancialMetric,
            "analytics.read", None, (),
            ("metric_type", "period_start", "period_end", "value", "calculated_at"),
        ),
        WorkspaceDomain(
            "risk", "Risk register", "Operational risk ownership and mitigation", "△", RiskRegisterEntry,
            "risk.read", "risk.manage",
            ("title", "description", "likelihood", "impact", "mitigation", "review_date", "status"),
            ("title", "likelihood", "impact", "review_date", "status"),
        ),
        WorkspaceDomain(
            "access", "Access & roles", "Organization memberships and assigned roles", "⌘", OrganizationMembership,
            "organization.manage", "organization.manage",
            ("user", "role", "is_active"),
            ("user", "role", "is_active"),
        ),
    )
}
