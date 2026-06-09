# Payroll data security and retention

## Sensitive data boundaries

General employee profile, employment, qualification, and compensation records are separated from restricted records in
`EmployeePersonalInformation`, `EmployeeBankAccount`, and `EmployeeTaxProfile`. Application services and APIs must require
the dedicated `view_*_information` / `change_*_information` permissions before loading or exposing those models. Never
serialize restricted models through a general employee endpoint, include their values in logs, or expose unrestricted admin
search fields.

The database and backups must use encryption at rest. In addition, the following values require **application-level envelope
encryption** with keys held outside the database:

- legal name, date of birth, personal contact details, residential address, and emergency contact;
- bank account-holder and routing details;
- tax elections and any tax data that must later be recovered.

The following values require **vault tokenization** and must never be persisted in plaintext:

- government, organization, client, and employee tax identifiers;
- bank account numbers;
- insurance policy numbers.

Where duplicate detection is required, store a separately keyed, non-reversible HMAC fingerprint. A fingerprint is not an
authentication secret and must not be used to reconstruct or display the source value. Rotate encryption and fingerprint keys
under a documented key-management procedure. Access to decryption/token-resolution services must be audited.

## Effective dates and historical payroll

Salary, benefit enrollment, deduction, commission plan, insurance coverage, tax profile, employment history, contract, and
employee-product assignment rows are effective-dated. Do not update a historical row after payroll consumes it. Close the old
period and create a new row. Model validation rejects overlapping periods; callers must invoke `full_clean()` before save, and
writes should be serialized per employee when concurrent changes are possible.

## Retention and deletion

Business, employee, and payroll inputs use `archived_at` and `retention_until` instead of destructive deletion. Archive records
when no longer operationally active. A scheduled retention process may permanently purge them only after `retention_until`,
after checking applicable employment, payroll, tax, litigation-hold, and jurisdictional requirements. Foreign-key protection
intentionally prevents deleting records referenced by historical payroll data. Sensitive token-vault values and encryption
keys must follow the same approved retention schedule; deleting a token or key early can make legally required records unusable.

## Secure documents and compliance audit events

Document metadata is organization-scoped and separates the business record from one or more private attachments. Attachments
are stored through the `private` Django storage alias, whose local development backend is outside both static and public media
roots. Production deployments should replace that alias with a private object-store backend and permit retrieval only through
the authorized protected-download endpoint or short-lived signed delivery URLs. Never expose the private bucket as a website.

All uploads must use `apps.documents.services.uploads.create_attachment`; it enforces the configured byte limit, checks the
declared MIME type against the extension and file signature, rejects known unsafe signatures, calculates SHA-256, and assigns a
random storage key. Deployments should extend the scanner with a managed malware-scanning service before accepting additional
file formats. Files that have not reached a clean scan status must never be delivered.

Personal and financial records carry retention dates. An active legal hold always blocks retention purge. Redaction requests
require a separate approval step, and document exports include a SHA-256 manifest. Compliance actions and highly sensitive reads
must call the auditing service so the actor, tenant, request ID, source address, affected object, summaries, and integrity chain
are retained. Audit events are append-only; database roles used by the application should not have UPDATE or DELETE rights on
the audit-event table, and exported reports should be verified against their included SHA-256 metadata.
