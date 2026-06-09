# Project scope

## Product statement

Payflow is a multi-organization payroll operations platform for managing workforce records, payroll periods, financial workflows,
documents, audit evidence, analytics, operational risk, and role-based access. It provides a browser workspace, versioned APIs,
background processing, and a locally hosted Ollama operations assistant.

The platform is currently an extensible operational foundation. It is not yet a certified payroll processor, banking platform,
tax filing service, or autonomous decision-making system.

## Target users

| User | Primary needs |
| --- | --- |
| Organization administrator | Configure organization access, oversee operations, documents, finance, audit, and risk |
| Payroll operator | Maintain employee and client records and prepare payroll operations |
| Employee | Read authorized payroll, document, finance, and analytics information |
| Auditor | Review immutable evidence, export authorized data, and append audit annotations |
| Client | Review authorized payroll, finance, document, audit, and analytics information |

## Implemented scope

### Platform and access

- Custom account model with optional MFA state, failed-login lockout, and idle session expiry.
- Multi-organization membership with administrator, payroll operator, employee, auditor, and client roles.
- Centralized `ROLE_ACTIONS` authorization and organization-scoped querysets.
- Role-aware browser workspace and versioned Django REST Framework APIs.

### Operational domains

- Organization, employee, client, compensation, payroll, taxation, finance, document, audit, analytics, and risk domain apps.
- Effective-dated payroll inputs and immutable payroll snapshots.
- Payroll lifecycle services and auditable approvals.
- Restricted-data models, document access classifications, retention controls, and append-only audit events.
- Financial accounts, metrics, forecasting foundations, reports, and exports.

### Operations assistant

- Local Ollama integration with tool-capable chat models.
- Role-filtered operation allowlist and organization-scoped execution.
- Workspace summaries and recent-record listings.
- Confirmation-gated audit-note and risk-entry creation.
- Short-lived signed confirmation payloads and audit events for completed writes.
- Graceful degradation when Ollama is unavailable.

### Runtime and delivery

- Docker Compose development stack with Django, PostgreSQL, Redis, Celery worker, and Celery beat.
- Development, testing, and production settings.
- OpenAPI schema and Swagger UI.
- Health endpoint, production security settings, and operational runbooks.

## Near-term scope

The next product increment should make the existing foundation reliable and usable for a controlled pilot:

1. Resolve the known failing repository tests and enforce a green CI baseline.
2. Complete payroll-run browser workflows, validation feedback, approvals, and reconciliation.
3. Add assistant tools for safe payroll preparation and operational reporting, with confirmation and audit controls.
4. Add assistant conversation persistence, request correlation, usage metrics, and administrator controls.
5. Improve dashboards, filtering, pagination, exports, notifications, and accessibility.
6. Complete jurisdiction-specific tax rules only after legal and payroll review.
7. Add production observability, backup automation, restore verification, and deployment automation.

## Out of scope without a separate approved project

- Moving money, initiating bank transfers, or storing raw banking credentials.
- Filing taxes or submitting statutory reports directly to government systems.
- Fully autonomous payroll approval, payment, termination, compensation, or access-control decisions.
- Training external AI models on tenant data.
- Exposing sensitive payroll or personal information to unapproved external model providers.
- Supporting a new jurisdiction without reviewed tax rules, legal requirements, and regression fixtures.
- Replacing professional payroll, accounting, legal, privacy, or security review.

## Product principles

- Tenant isolation and least privilege are mandatory, not optional features.
- Financial and payroll outcomes must remain reproducible and explainable.
- High-impact writes require explicit human confirmation and audit evidence.
- AI proposes and assists; deterministic services authorize and execute.
- Sensitive data exposure is minimized across APIs, logs, exports, and model prompts.
- Regulatory claims require evidence and jurisdiction-specific review.

## Success measures

| Area | Initial target |
| --- | --- |
| Authorization | No cross-organization access in automated security-boundary tests |
| Payroll integrity | Reproducible calculations and lifecycle transitions for approved jurisdictions |
| Reliability | Green CI baseline and documented recovery objectives |
| Auditability | All privileged writes attributable to actor, organization, operation, and time |
| Assistant safety | No write without server-side authorization and explicit confirmation |
| Usability | Core pilot workflows complete without Django admin access |
