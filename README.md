# Payflow Payroll Management Platform

Payflow is a multi-organization payroll operations platform built with Django. It combines workforce and payroll records,
financial workflows, secure documents, audit evidence, analytics, operational risk, role-based access, and a locally hosted
Ollama operations assistant.

The repository is an extensible operational foundation. It is not yet a certified payroll processor, tax filing service, banking
platform, or autonomous decision-making system. See the [project scope](docs/project-scope.md) and
[delivery plan](docs/project-plan.md) for the current boundaries and roadmap.

## Capabilities

- Multi-organization tenancy with centralized role-based authorization.
- Browser workspace for employees, clients, payroll, documents, finance, audit, analytics, risk, and access management.
- Versioned REST APIs and generated OpenAPI documentation.
- Effective-dated payroll inputs, lifecycle services, immutable calculation evidence, and approvals.
- Sensitive-data separation, document retention controls, and tamper-evident audit events.
- PostgreSQL persistence, Redis-backed Celery tasks, and scheduled jobs.
- Ollama assistant with role-filtered tools, organization scoping, confirmation-gated writes, and audit logging.

## Documentation

| Document | Purpose |
| --- | --- |
| [Documentation index](docs/README.md) | Guide to all project documentation |
| [Project scope](docs/project-scope.md) | Goals, users, implemented features, boundaries, and success measures |
| [Delivery plan](docs/project-plan.md) | Stabilization priorities, roadmap phases, and technical debt |
| [Architecture](docs/architecture.md) | Components, data flow, RBAC, assistant trust boundaries, and deployment |
| [Security](docs/security.md) | Security controls and engineering requirements |
| [Data security](docs/data-security.md) | Sensitive-data handling and retention |
| [Privacy](docs/privacy.md) | Privacy workflows and requirements |
| [Operations](docs/operations.md) | Production readiness, monitoring, backup, recovery, and incidents |

## Architecture

Payflow is a domain-oriented Django monolith. PostgreSQL is the system of record, Redis is the Celery broker, Celery workers and
beat handle asynchronous work, and Django REST Framework exposes APIs at `/api/v1/`.

```text
Browser / API client
        |
        v
   Django web app <------> Ollama
        |
        +----> PostgreSQL
        +----> Redis <---- Celery worker / beat
        +----> File storage
```

Domain apps live under `apps/`, platform routing and configuration under `payroll_platform/`, and browser assets under
`templates/` and `static/`. Read the [architecture guide](docs/architecture.md) for the complete design.

## Requirements

- Docker with Compose, recommended for development
- Ollama with a tool-capable model for assistant features
- For local non-Docker development: Python 3.13+, PostgreSQL 17+, and Redis 8+

## Quick start

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_browser_demo
```

Open:

- Application: <http://localhost:8000/>
- Login: <http://localhost:8000/login/>
- Workspace: <http://localhost:8000/dashboard/>
- API documentation: <http://localhost:8000/api/docs/>
- Health check: <http://localhost:8000/health/>

The Compose stack starts Django, PostgreSQL, Redis, a Celery worker, and Celery beat.

## Demo accounts

Run `docker compose exec web python manage.py seed_browser_demo` to create representative data and role accounts. All demo users
use password `Demo123!Pass`.

| Username | Role |
| --- | --- |
| `administrator` | Organization administrator |
| `payroll-operator` | Payroll operator |
| `employee` | Employee |
| `auditor` | Auditor |
| `client` | Client |

Workspace navigation is generated from the centralized `ROLE_ACTIONS` map. Every request also performs server-side organization
and action authorization; hidden navigation is not treated as an access control.

## Ollama assistant

Install and start a tool-capable Ollama model:

```bash
ollama pull llama3.2
ollama serve
```

Docker Compose defaults to:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2:latest
```

The assistant currently supports authorized workspace summaries, recent-record listings, audit-note creation, and risk-entry
creation. The model only sees tools allowed for the user's role. The server repeats RBAC and tenant checks during execution, and
writes require a short-lived signed confirmation before they are performed and audited.

## Configuration

Configuration is read from environment variables. `.env.example` documents available values; never commit `.env` or credentials.

| Variable | Purpose | Development default |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Django signing and cryptographic secret | Unsafe development placeholder |
| `DEBUG` | Django debug mode | `false` in base, `true` in development |
| `DATABASE_URL` | PostgreSQL connection | Local payroll database |
| `CELERY_BROKER_URL` | Redis broker | `redis://localhost:6379/0` |
| `DJANGO_TIME_ZONE` | Application time zone | `UTC` |
| `OLLAMA_BASE_URL` | Ollama API URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Tool-capable assistant model | `llama3.2:latest` |
| `OLLAMA_TIMEOUT_SECONDS` | Ollama request timeout | `30` |
| `ASSISTANT_CONFIRMATION_MAX_AGE` | Write-confirmation lifetime in seconds | `300` |

## Local development without Docker

Start PostgreSQL and Redis, then:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/development.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Run Celery in separate terminals:

```bash
celery -A payroll_platform worker --loglevel=info
celery -A payroll_platform beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## Testing and quality

```bash
ruff format --check .
ruff check .
DJANGO_SETTINGS_MODULE=payroll_platform.settings.testing python manage.py test
bandit -q -r apps payroll_platform -x '*/migrations/*'
pip-audit -r requirements/base.txt
```

The current repository has known full-suite failures documented in the [delivery plan](docs/project-plan.md). Resolve these before
a controlled pilot or production deployment.

## Production

The Compose topology is for development. Production requires managed data services, immutable images, TLS, secrets management,
private file storage, centralized logs and metrics, alerting, backup verification, restore exercises, and security review.
Follow the [operations runbook](docs/operations.md), [security guide](docs/security.md), and
[data-security guide](docs/data-security.md).

## License

See [LICENSE](LICENSE).
