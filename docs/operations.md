# Production operations, incident response, backup, and disaster recovery

## Production readiness and privileged access

Before launch, complete a threat-model review, data inventory, processor/vendor assessment, penetration test, restore test,
runbook exercise, and jurisdiction-specific legal/accounting sign-off. Enable production calculations only for jurisdictions
listed in `LEGAL_REVIEW_APPROVED_JURISDICTIONS`. Production access requires SSO, phishing-resistant MFA, named accounts,
just-in-time elevation, ticketed purpose, and centralized audit logs. Review privileged users, service accounts, database roles,
cloud roles, break-glass accounts, and token-vault access monthly and after every role change; remove access within 24 hours of
termination or transfer. Test break-glass access quarterly and rotate it after each use.

## Monitoring and alerting

Collect application, proxy, identity, database, cache, object-store, KMS, CI/CD, and cloud control-plane logs in a separate,
append-resistant security account. Do not log restricted values. Monitor uptime, latency, error rate, queue depth, failed jobs,
replication lag, backup age, restore verification, certificate expiry, disk/storage capacity, 429s, lockouts, MFA failures,
privilege changes, sensitive exports/reads, legal-hold changes, audit-chain failures, and key/vault errors.

Page the on-call immediately for suspected data exposure, privilege escalation, ransomware, payroll-integrity failure, audit-log
failure, unavailable primary service, failed backups beyond RPO, or certificate/key compromise. Create a ticket for threshold
warnings and track them to closure. Test alert routing monthly.

## Backup and restore

| Data | Schedule | Retention | Verification |
| --- | --- | --- | --- |
| PostgreSQL | encrypted continuous WAL/PITR plus daily snapshot | 35 daily, 12 monthly, 7 annual or approved local schedule | automated daily integrity check; isolated restore monthly |
| Private documents/token-vault references | versioned replication plus daily inventory | same approved record retention; legal holds override expiry | daily inventory/hash comparison; sampled restore monthly |
| Configuration/audit exports | on every change plus daily encrypted export | approved audit/config schedule | signature/hash verification daily |

Backups must be encrypted with keys separate from workload credentials, immutable against the runtime role, replicated to an
approved separate account/region, and monitored. Backup operators cannot unilaterally restore into production.

Restore procedure: declare incident/change; identify approved recovery point; provision an isolated clean environment; restore
secrets/configuration from authoritative stores; restore database and private objects; verify schemas, row/object counts, hashes,
audit-chain continuity, malware status, and key/token resolution; run smoke/payroll reconciliation tests; replay approved privacy
deletions since the recovery point; obtain incident commander and business-owner approval; then cut over and monitor closely.
Record actual recovery-point loss and elapsed recovery time.

## Recovery objectives and disaster recovery

Target **RPO: 15 minutes** for payroll/database/audit data and **RTO: 4 hours** for the core payroll service, subject to business
impact review and vendor capabilities. Supporting analytics may use RPO 24 hours/RTO 24 hours. If testing cannot meet an objective,
record the gap, owner, compensating control, and due date. Run an isolated restore monthly, tabletop incident exercise quarterly,
and full regional failover at least annually. DR exercises must include key/vault availability, private documents, queued jobs,
identity, DNS/certificates, reconciliation, privacy-deletion replay, and return-to-primary.

## Incident response

1. **Detect and declare:** page on-call, open a restricted incident record, assign commander, security lead, communications lead,
   and scribe; preserve timestamps and evidence.
2. **Contain:** revoke sessions/tokens, disable compromised accounts/integrations, isolate workloads, block abuse, and preserve
   forensic snapshots. Do not destroy evidence or rotate encryption keys before confirming recovery implications.
3. **Assess:** determine affected tenants, people, fields, jurisdictions, payroll integrity, time window, and processors. Engage
   counsel, privacy, accounting/payroll, insurer, and law enforcement as appropriate.
4. **Eradicate and recover:** patch root cause, rotate exposed secrets, rebuild from trusted artifacts, restore/verify as above,
   reconcile payroll/tax outputs, and increase monitoring.
5. **Notify:** counsel determines contractual/regulatory/individual notification content and deadlines. Never delay escalation while
   waiting for perfect certainty.
6. **Learn:** complete a blameless review within ten business days, track corrective actions, update this runbook/threat model,
   and retain evidence under legal direction.
