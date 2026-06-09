# Project delivery plan

## Current baseline

The repository has a broad domain model, API surface, role-aware browser workspace, Docker runtime, security controls, operational
documentation, and an Ollama-powered operations assistant. The application runs locally, but the full automated test suite has
known failures outside the assistant feature. A controlled pilot should not begin until the stabilization phase is complete.

## Phase 0: Stabilize the foundation

**Priority:** Immediate

Deliverables:

- Fix all existing test-suite failures and make CI required for merge.
- Resolve API authorization-order issues so unauthorized callers consistently receive `403`.
- Verify encryption, privacy deletion, payroll lifecycle, taxation error, and audit annotation behavior.
- Add linting, migration checks, security scanning, dependency auditing, and coverage gates to CI.
- Define supported Python, PostgreSQL, Redis, Ollama, and model versions.

Exit criteria:

- Full test suite passes from a clean checkout.
- No known critical or high-severity security defects.
- Development setup and demo seeding work from documented commands.

## Phase 1: Complete controlled payroll operations

**Priority:** High

Deliverables:

- Guided payroll preparation, validation, approval, lock, payment-recording, correction, and archive workflows.
- Clear browser validation errors and lifecycle status history.
- Reconciliation views for inputs, calculation runs, payslips, and payment batches.
- Role-specific dashboards, search, filters, pagination, exports, and notifications.
- Expanded integration tests around payroll integrity and organization isolation.

Exit criteria:

- A payroll operator and administrator can complete a representative payroll lifecycle without Django admin.
- Every transition is authorized, validated, reproducible, and auditable.

## Phase 2: Expand the operations assistant

**Priority:** High after stabilization

Deliverables:

- Assistant tools for payroll readiness checks, exception summaries, document follow-up, and operational reporting.
- Structured tool results and deterministic service-layer execution.
- Conversation persistence with retention controls and request correlation.
- Per-organization assistant enablement, model selection, tool policies, and usage limits.
- Prompt-injection tests, sensitive-field filtering, audit dashboards, and tool-level telemetry.

Exit criteria:

- Every tool has explicit RBAC, tenant-isolation, validation, confirmation, audit, and automated abuse tests.
- The assistant cannot directly access arbitrary models, execute code, or bypass domain services.

## Phase 3: Production readiness and pilot

**Priority:** Medium

Deliverables:

- Managed PostgreSQL, Redis, private object storage, secrets management, and centralized logging.
- Metrics, traces, alerting, queue monitoring, audit-chain verification, and model availability monitoring.
- Automated backups, restore tests, disaster-recovery exercise, and incident-response exercise.
- Accessibility review, performance testing, penetration testing, and privacy impact assessment.
- Pilot onboarding, support procedures, and operator training.

Exit criteria:

- Production readiness review is approved.
- Recovery and incident exercises meet documented objectives.
- Pilot scope and supported jurisdictions are explicitly approved.

## Phase 4: Integrations and jurisdiction expansion

**Priority:** Future

Potential deliverables:

- Reviewed tax engines and statutory reporting for additional jurisdictions.
- Approved accounting, HRIS, identity-provider, and payment-provider integrations.
- Webhooks, import pipelines, and integration reconciliation.
- Advanced forecasting, anomaly detection, and compliance reporting.

Each integration or jurisdiction requires its own threat model, data-flow review, legal review, test fixtures, reconciliation
strategy, and operational ownership.

## Cross-cutting workstreams

| Workstream | Ongoing requirements |
| --- | --- |
| Security | Threat modeling, dependency management, least privilege, penetration tests, and incident readiness |
| Data governance | Classification, minimization, retention, deletion, legal holds, and export controls |
| Quality | Unit, integration, authorization-boundary, payroll-reconciliation, and recovery testing |
| Operations | Observability, capacity planning, backup verification, runbooks, and support readiness |
| Documentation | Keep scope, architecture, API docs, runbooks, and user guidance aligned with releases |

## Known technical debt

- The full repository test suite currently contains failures that must be resolved before pilot use.
- The browser workspace is intentionally generic and needs domain-specific payroll workflows.
- Assistant operations are currently synchronous and use a small hard-coded tool allowlist.
- Assistant conversations are not persisted and model health is not included in the application health endpoint.
- Docker Compose is a development topology, not a production deployment architecture.
- Several UI strings contain encoding artifacts and need normalization.

## Change-control rule

Changes affecting payroll calculations, tax behavior, authorization, sensitive data, audit evidence, assistant tools, or retention
must include tests, documentation updates, named reviewers, and an explicit rollback or remediation plan.
