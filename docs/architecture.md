# Architecture

## Overview

Payflow is a domain-oriented Django monolith. The design keeps payroll transactions, authorization, audit evidence, and related
workflows in one deployable application while separating business capabilities into bounded Django apps. This avoids distributed
transaction complexity during the current product stage and leaves clear service boundaries for future extraction.

## System context

```text
Browser users / API clients
          |
          v
 Django web application  <------>  Ollama server
          |
          +------> PostgreSQL
          |
          +------> Redis <------ Celery worker / Celery beat
          |
          +------> Private and static file storage
```

Ollama is an optional supporting service. Core payroll and workspace operations remain available when it is unavailable.

## Major components

| Component | Responsibility |
| --- | --- |
| `payroll_platform/` | Root routing, settings, workspace registry, assistant orchestration, Celery, WSGI, and ASGI |
| `apps/accounts` | Identity, authentication, lockout, session security, and MFA state |
| `apps/organizations` | Tenants, memberships, roles, scoped querysets, and central authorization |
| `apps/employees`, `apps/clients`, `apps/compensation` | Workforce, client, and compensation records |
| `apps/payroll`, `apps/taxation`, `apps/finance` | Payroll lifecycle, calculations, tax rules, financial records, forecasting, and reports |
| `apps/documents`, `apps/auditing` | Classified documents, retention, immutable events, annotations, and exports |
| `apps/analytics`, `apps/risk` | Metrics, dashboards, forecasts, and operational risk |
| `templates/`, `static/` | Server-rendered workspace and shared browser assets |

## Request paths

### Browser workspace

1. Django authenticates the session and applies idle-timeout and security middleware.
2. The workspace selects an active organization available to the user.
3. `authorize(user, organization, action)` verifies the requested operation.
4. Organization-scoped querysets restrict records to accessible tenants.
5. Domain services validate and persist changes.
6. Privileged or significant changes create audit evidence.

### Versioned API

API clients use `/api/v1/`. Django REST Framework authenticates the caller, organization mixins and service-layer authorization
enforce tenant access, serializers validate input, and domain services perform business operations.

### Background work

Celery workers consume tasks from Redis. Celery beat schedules recurring tasks. Tasks must receive stable identifiers rather than
trusted model instances, reload records with organization scope, and repeat authorization or policy checks appropriate to the job.

## Data architecture

PostgreSQL is the system of record. Tenant-owned models inherit `OrganizationScopedModel`, and callers should begin with
`.for_user(user)` before applying organization filters. Payroll inputs that change over time use effective dates. Calculation
runs, approvals, payslips, payment batches, and audit events preserve immutable evidence needed for reproduction and review.

Restricted personal, banking, tax, and document data is separated from ordinary operational records and governed by dedicated
permissions and retention rules. See [data security and retention](data-security.md).

## Authorization architecture

`OrganizationMembership` links a user to an organization and role. `ROLE_ACTIONS` maps each role to explicit operations such as
`employee.read`, `payroll.write`, or `risk.manage`.

Authorization is enforced at several layers:

- Navigation only shows relevant areas for usability.
- Views and APIs call the central authorization service.
- Querysets enforce organization scoping.
- Domain services validate lifecycle and business rules.
- Audit events record sensitive and privileged activity.

Hidden navigation is never considered an access control.

## Operations assistant architecture

The assistant is implemented in `payroll_platform/assistant.py` and exposed through the authenticated `/assistant/chat/` endpoint.
The browser widget sends a selected organization, recent conversation context, and the user's request.

```text
User prompt
   |
   v
Authenticated assistant endpoint
   |
   +--> Resolve organization membership and role
   +--> Expose only allowed tool schemas to Ollama
   |
   v
Ollama selects a tool or returns text
   |
   +--> Read tool: authorize, scope, execute, format result
   |
   +--> Write tool: issue signed short-lived proposal
                         |
                         v
                    User confirms
                         |
                         v
              Verify signature, user, tenant, RBAC,
              validate domain object, write, audit
```

The model is not an authorization authority and does not receive database credentials. It cannot execute arbitrary code or query
arbitrary models. Tool execution remains deterministic and server controlled. Current tools provide summaries, list recent
records, append audit notes, and create risk entries.

### Assistant trust boundaries

- Prompt text and model output are untrusted.
- Tool names and arguments are validated against an allowlist.
- Available tools are filtered by role, then re-authorized during execution.
- All records are scoped to the selected organization.
- Writes require a signed confirmation tied to the user and organization.
- Completed writes generate audit evidence.
- Sensitive-field filtering must be added before exposing tools that handle restricted data.

## Deployment architecture

The development topology uses Docker Compose:

- `web`: Django development server.
- `db`: PostgreSQL.
- `redis`: Celery broker.
- `worker`: Celery worker.
- `beat`: Celery scheduler.
- Ollama runs on the host and is reached through `host.docker.internal`.

Production should use an immutable web image behind a TLS-terminating proxy or load balancer, managed PostgreSQL and Redis,
separate worker processes, private object storage, a secrets manager, centralized logs, metrics, alerting, and controlled access
to an approved model runtime.

## Architectural decisions

| Decision | Rationale |
| --- | --- |
| Domain-oriented monolith | Preserves transactional consistency and reduces operational complexity at the current scale |
| Central action-based RBAC | Makes browser, API, service, and assistant authorization consistent |
| Organization-scoped models | Establishes a reusable tenant-isolation convention |
| Immutable payroll and audit evidence | Supports reproducibility, reconciliation, and compliance review |
| Local Ollama model runtime | Keeps model operation under operator control and avoids default external data transfer |
| Allowlisted assistant tools | Prevents free-form model access to application internals |
| Confirmation-gated assistant writes | Keeps a human decision point for operational changes |

## Evolution guidelines

- Add behavior to domain services before exposing it through browser views, APIs, or assistant tools.
- Do not extract a service until there is a clear ownership, scaling, security, or deployment requirement.
- Use an outbox or equivalent reliable event pattern before introducing cross-service workflows.
- Treat new assistant tools as privileged API endpoints requiring threat modeling and authorization tests.
- Record material architectural changes as decision records under a future `docs/decisions/` directory.
