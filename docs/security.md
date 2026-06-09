# Security architecture and threat model

## Scope and ownership

This document applies to the payroll web application, workers, PostgreSQL, Redis, private document storage, backups, CI/CD,
and administrator access. The security owner approves production changes, key rotation, exceptions, and incident closure. Every
production deployment must pass `python manage.py check --deploy`, CI security jobs, and a change review.

## Threat model

| Asset | Principal threats | Required controls |
| --- | --- | --- |
| Credentials, sessions, MFA seeds | credential stuffing, phishing, session theft, offline cracking | Argon2, MFA, lockout, auth rate limit, secure/HttpOnly/Strict cookies, short reset lifetime, idle timeout |
| Employee PII, tax and bank data | tenant breakout, SQL/database theft, excessive privilege, log leakage | organization scoping, least privilege, audited access, field encryption/tokenization, TLS, encrypted database/backups |
| Payroll inputs/results | unauthorized modification, replay, calculation-rule error | role checks, idempotency, immutable snapshots, approvals, audit chain, jurisdiction approval gate |
| Documents and exports | public-object exposure, malware, excessive retention | private storage, signature/type checks, malware scan integration, short-lived delivery, legal holds, retention workflows |
| Secrets and encryption keys | source-control leak, worker/environment compromise | managed secret store, workload identity, no committed secrets, key rotation, secret scanning |
| Service availability | abusive requests, dependency failure, ransomware, regional outage | rate limiting, monitoring, tested backups/restores, DR exercises |

Trust boundaries are the public TLS endpoint, application-to-database/cache/object-store connections, CI/CD-to-production,
and privileged human access. The reverse proxy must replace—not append untrusted values to—forwarding headers. Production
must use a shared cache for rate limits; the local-memory cache is not sufficient across replicas. Abuse controls complement,
but do not replace, upstream WAF and identity-provider controls.

## Mandatory production controls

- Terminate TLS 1.2+ at the approved load balancer and use TLS for database, Redis, object store, mail, and third-party calls.
  Redirect HTTP, enable HSTS only after validating all subdomains, and restrict trusted proxy sources.
- Load `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEYS`, `DATA_FINGERPRINT_KEY`, database credentials, and vendor tokens from the
  managed secret store at runtime. Do not place production values in `.env`, images, CI logs, or source control.
- Keep the current field-encryption key first and previous decrypt-only keys after it during rotation. Re-encrypt records, verify,
  then retire old keys. Run `python manage.py reencrypt_sensitive_data` after deployment and during key rotation. Tokenized identifiers and account numbers must resolve only through an audited vault service.
- Use separate least-privilege database roles for migrations, runtime, reporting, and backup. Deny runtime UPDATE/DELETE on the
  audit-event table. Encrypt primary storage, replicas, snapshots, object storage, and backup media with managed KMS keys.
- Run production behind a shared-cache rate limit and edge WAF. Alert on lockouts, 429 spikes, failed MFA, anomalous exports,
  sensitive-record reads, role changes, and encryption/decryption failures.

The `EncryptedTextField` protects recoverable values against raw database/back-up disclosure. Deterministic HMAC fingerprints
support duplicate lookup without making the source value recoverable. Token fields are references only: integrating an approved
external token vault is required before storing real bank, government, tax, insurance, or client identifiers.

## Secure development and verification

CI performs dependency vulnerability scanning, Bandit static analysis, Gitleaks secret scanning, migration-drift checks,
Django deployment checks, and tests. Findings block merge unless the security owner documents an expiration-dated exception.
Patch critical exploitable findings immediately; triage high findings within one business day. Rotate any exposed secret even
if logs or Git history are later rewritten.

## Regulated calculation release gate

Production tax and payroll calculations fail closed unless the jurisdiction appears in `LEGAL_REVIEW_APPROVED_JURISDICTIONS`.
A jurisdiction may be added only after written review by qualified local legal counsel and accounting/payroll professionals,
with evidence covering tax, payroll, employment, investment, insurance, reporting, rounding, effective dates, and retention.
Generic financial, investment, commission, or insurance outputs must remain decision-support-only until the same review and
product approval are complete. Re-review after rule, jurisdiction, or product changes and at least annually.
