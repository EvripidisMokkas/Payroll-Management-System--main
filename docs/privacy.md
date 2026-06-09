# Privacy, classification, retention, and data-subject procedures

## Classification and handling

| Class | Examples | Handling |
| --- | --- | --- |
| Restricted | government/tax IDs, bank numbers, MFA seeds, tax elections, DOB, residential address, payroll results | least privilege; TLS; encrypted/tokenized at rest; audited access; never log; approved export only |
| Confidential | employee contact details, compensation, contracts, documents, client and organization financials | tenant scoped; TLS; encrypted storage/backups; access logged where sensitive |
| Internal | operational metadata, non-sensitive configuration, aggregate metrics | authenticated access; integrity controls |
| Public | intentionally published material | publication approval |

Data owners inventory fields and processors before collection. Collect only what has a documented purpose and lawful basis.
Never copy production restricted data to development or support tickets. Exports are restricted data and require encryption,
short expiry, recipient verification, and an audit record.

## Retention policy

The privacy owner and jurisdiction-specific counsel maintain an approved retention schedule by record category and country/state.
Until that schedule exists, records are retained and deletion is disabled. Payroll runs, payslips, tax filings, audit evidence,
accounting entries, approvals, and records under legal hold are legally required evidence and must not be destructively changed.
Operational PII should be archived when no longer needed, assigned `retention_until`, and purged only after expiry and a legal-hold
check. Backups expire on their independent schedule; deleted data is not restored into production except for disaster recovery,
and any restored deletion requests must be replayed before normal processing resumes.

Recommended baseline pending approved local schedules (not legal advice): active employment plus the longest applicable payroll,
tax, accounting, employment, limitation, and litigation-hold period; support/security logs 90–365 days according to purpose;
failed uploads and temporary exports no longer than 30 days. Counsel must replace these baselines with exact requirements.

## Data-subject workflow

1. Record an export, correction, deletion, or retention-review request and verify the requester's identity using an approved
   out-of-band process. Never ask for additional full identifiers when partial verification is sufficient.
2. Search all tenant-scoped systems, processors, documents, and backups. Document jurisdiction, lawful basis, deadline,
   exemptions, legal holds, and records that must be preserved.
3. Require independent approval. The requester cannot execute their own request; the executor needs the privacy-workflow
   permission. Record every action in the immutable audit log.
4. **Export:** use `export_employee_data`; review the generated package, encrypt it, validate its SHA-256, and deliver it through
   an authenticated short-lived channel. It includes a notice identifying preserved payroll evidence.
5. **Correction:** use `correct_employee_data` for approved profile fields. Correct legally material payroll/tax history using a
   versioned correction or adjustment, never by overwriting immutable snapshots.
6. **Deletion/minimization:** use `delete_employee_data`. It blanks operational contact/restricted PII and archives records while
   preserving the employee key and protected payroll/tax evidence. Token-vault deletion must follow the approved retention date.
7. Confirm completion, explain exemptions/preserved categories, and retain the request/audit evidence itself under the approved
   privacy-compliance schedule.

A request must stop and be escalated when identity cannot be verified, litigation hold exists, records are disputed, a statutory
retention requirement applies, or deletion would undermine another person's rights or required payroll/accounting evidence.
