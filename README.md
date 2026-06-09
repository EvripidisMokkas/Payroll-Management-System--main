# Payroll Management Platform

A modular Django foundation for payroll operations, workforce management, financial workflows, compliance, reporting, and risk analysis.

## Architecture

The platform uses a domain-oriented monolith that can evolve without prematurely splitting operational workflows across services:

- `payroll_platform/` contains root URL routing, Celery setup, and environment-specific settings.
- `apps/` contains bounded Django apps for accounts, organizations, employees, clients, payroll, taxation, finance, documents, auditing, analytics, and risk.
- `templates/` and `static/` provide shared server-rendered UI resources.
- PostgreSQL is the system of record; Redis is the Celery broker; Celery workers and beat process asynchronous and scheduled jobs.
- Django REST Framework provides versioned APIs at `/api/v1/`, and drf-spectacular publishes OpenAPI schema and Swagger UI.
- WhiteNoise serves versioned static assets in production. Gunicorn runs the production WSGI application.

### Settings environments

| Environment | Module | Purpose |
| --- | --- | --- |
| Development | `payroll_platform.settings.development` | Debugging, local PostgreSQL, console email |
| Testing | `payroll_platform.settings.testing` | In-memory SQLite, eager Celery tasks, fast password hashing |
| Production | `payroll_platform.settings.production` | Required secret/hosts, HTTPS redirects, secure cookies, HSTS |

## Requirements

- Python 3.13+
- PostgreSQL 17+
- Redis 8+
- Docker with Compose (recommended for local development)

Dependencies are pinned in `requirements/base.txt`, with development and testing additions in their corresponding files. The stack includes Django, psycopg, Django REST Framework, Celery, Redis, OpenAPI tooling, Matplotlib, ReportLab, and OpenPyXL.

## Quick start with Docker

```bash
cp .env.example .env
# Replace all placeholder secrets in .env before using shared environments.
docker compose build
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
docker compose up
```

Open:

- Application: <http://localhost:8000/>
- Browser login: <http://localhost:8000/login/>
- Role-aware operations workspace: <http://localhost:8000/dashboard/>
- Admin: <http://localhost:8000/admin/>
- API documentation: <http://localhost:8000/api/docs/>
- Health check: <http://localhost:8000/health/>

The Compose stack starts the Django development server, PostgreSQL, Redis, a Celery worker, and Celery beat. Stop it with `docker compose down`; add `--volumes` to delete local database and Redis data.

### Browser workspace and RBAC demo

Seed a representative organization, operational records, and one account for each organization role:

```bash
docker compose exec web python manage.py seed_browser_demo
```

All demo users use the password `Demo123!Pass`:

| Username | Browser capabilities |
| --- | --- |
| `administrator` | Full organization workspace, employees, clients, payroll, documents, finance, audit, risk, and role assignment |
| `payroll-operator` | Employee, payroll, document, client, finance, and analytics operations |
| `employee` | Read-only payroll, document, finance, and analytics access |
| `auditor` | Read-only payroll, employee, document, finance, audit, analytics, and risk access |
| `client` | Read-only payroll, document, finance, audit, and analytics access |

Workspace navigation is generated from the centralized `ROLE_ACTIONS` authorization map. Every browser request also performs server-side organization and action authorization; hiding a navigation item is not treated as an access control.

## Local setup without Docker

Start PostgreSQL and Redis locally, then:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/development.txt
cp .env.example .env
```

Update `.env` so `DATABASE_URL` and `CELERY_BROKER_URL` address local services (for example, `localhost` instead of Compose service names), then run:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

In separate terminals, run background services:

```bash
celery -A payroll_platform worker --loglevel=info
celery -A payroll_platform beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## Configuration

Configuration is read from environment variables; `.env.example` documents safe placeholders. Never commit `.env` or real credentials.

| Variable | Description | Development default |
| --- | --- | --- |
| `DJANGO_SETTINGS_MODULE` | Active settings module | `payroll_platform.settings.development` via `manage.py` |
| `DJANGO_SECRET_KEY` | Cryptographic signing secret; mandatory in production | Unsafe development placeholder |
| `DEBUG` | Enable Django debug mode | `false` in base, `true` in development |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames | `localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated HTTPS origins | Empty |
| `DATABASE_URL` | PostgreSQL connection URL | Local payroll database |
| `DATABASE_CONN_MAX_AGE` | Persistent DB connection lifetime in seconds | `60` |
| `CELERY_BROKER_URL` | Redis broker URL | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result storage | `django-db` |
| `DJANGO_TIME_ZONE` | Application time zone | `UTC` |
| `DJANGO_LOG_LEVEL` | Console logging threshold | `INFO` |

## Database migrations

Create and review migrations whenever models change:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
```

For deployment, run migrations once as a release task rather than concurrently in every web container. Back up PostgreSQL before destructive or irreversible changes.

## Testing and quality checks

Tests use the isolated testing settings module and do not require PostgreSQL or Redis:

```bash
ruff format --check .
ruff check .
mypy apps/payroll/services apps/taxation/services/engine.py apps/finance/services apps/organizations/services.py apps/organizations/mixins.py
DJANGO_SETTINGS_MODULE=payroll_platform.settings.testing python manage.py makemigrations accounts --check --dry-run
DJANGO_SETTINGS_MODULE=payroll_platform.settings.testing coverage run manage.py test
coverage report
coverage json
python scripts/check_high_risk_coverage.py
bandit -q -r apps payroll_platform -x '*/migrations/*,*/tests.py'
pip-audit -r requirements/base.txt
```

Run Django's production deployment checks with real production-style environment values:

```bash
DJANGO_SETTINGS_MODULE=payroll_platform.settings.production \
DJANGO_SECRET_KEY='replace-with-a-long-random-production-secret' \
DJANGO_ALLOWED_HOSTS='payroll.example.com' \
DATABASE_URL='postgresql://user:password@db:5432/payroll' \
python manage.py check --deploy
```

## Deployment

1. Build an immutable image from `Dockerfile` and publish it to a private registry.
2. Provision managed PostgreSQL and Redis with encryption, backups, monitoring, and network restrictions.
3. Inject production environment variables from a secrets manager. Set trusted hosts/origins and a unique, high-entropy secret key.
4. Run `python manage.py migrate --noinput` as a single release job.
5. Run `python manage.py collectstatic --noinput` while building or releasing the image.
6. Start web containers with the Dockerfile's Gunicorn command and separately start worker and beat processes.
7. Terminate TLS at the load balancer or proxy and forward `X-Forwarded-Proto`. The production settings enforce HTTPS, secure cookies, HSTS, and clickjacking protection.
8. Point liveness checks to `/health/`; add database and broker readiness checks appropriate for the hosting platform.
9. Centralize container logs and alert on application errors, failed tasks, resource pressure, and unusual access patterns.

For production image startup automation, set `RUN_MIGRATIONS=true` and/or `COLLECT_STATIC=true` only when the process is intentionally responsible for those one-time operations.

## Tenant authorization and account security

`accounts.User` is the platform's custom user model. Do not change `AUTH_USER_MODEL` or create application migrations that reference Django's built-in user model. Organization access is granted through `OrganizationMembership`; users may hold different roles in multiple organizations. The canonical administrator, payroll operator, employee, auditor, and client groups and explicit permissions are synchronized after migrations.

All tenant-owned models should inherit `OrganizationScopedModel`, callers should begin queries with `.for_user(user)`, and service/view code must call `authorize()` or use `OrganizationAccessMixin` before accessing a caller-supplied organization ID. Auditors are read-only except for append-only audit annotations.

Authentication endpoints are under `/api/v1/accounts/`. Optional TOTP MFA is enabled per account, failed passwords trigger temporary lockout, authenticated sessions expire after the configured idle period, and login rotates the session key. Relevant environment variables are `ACCOUNT_LOCKOUT_THRESHOLD`, `ACCOUNT_LOCKOUT_DURATION`, `SESSION_IDLE_TIMEOUT`, and `SESSION_COOKIE_AGE`.

## Payroll domain data model and sensitive-data handling

Organization, client, and employee records are organization-scoped. Payroll inputs that can change over time—including
salary, benefits, deductions, commissions, insurance, tax profiles, contracts, employment history, and product assignments—
are effective-dated so prior payroll calculations can be reproduced. Restricted banking, tax, and personal data is stored in
separate models with dedicated permissions. See [the data security and retention guide](docs/data-security.md) before building
services, serializers, exports, or retention jobs that access these records.
