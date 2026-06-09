"""Verified, auditable data-subject workflows that preserve payroll evidence."""

import hashlib
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from apps.auditing.models import AuditAction
from apps.auditing.services import record_event
from apps.payroll.models import EmployeePayrollInput

from ..models import (
    DataSubjectRequest,
    EmployeeBankAccount,
    EmployeePersonalInformation,
    EmployeeTaxProfile,
    PrivacyRequestStatus,
    PrivacyRequestType,
)

GENERAL_CORRECTION_FIELDS = {"preferred_name", "given_name", "family_name", "work_email", "work_phone"}
PERSONAL_CORRECTION_FIELDS = {
    "legal_name_encrypted",
    "date_of_birth_encrypted",
    "personal_email_encrypted",
    "personal_phone_encrypted",
    "residential_address_encrypted",
    "emergency_contact_encrypted",
}


def _authorize(request_record, actor):
    if request_record.status != PrivacyRequestStatus.APPROVED or request_record.approved_by_id is None:
        raise ValidationError("Privacy request must be independently approved before execution.")
    if actor.pk == request_record.requested_by_id:
        raise PermissionDenied("Requester cannot execute their own privacy request.")
    if not actor.has_perm("employees.manage_privacy_requests") and not actor.is_superuser:
        raise PermissionDenied("Privacy workflow permission is required.")


def create_request(*, employee, request_type, requested_by, reason=""):
    return DataSubjectRequest.objects.create(
        organization=employee.organization,
        employee=employee,
        request_type=request_type,
        requested_by=requested_by,
        reason=reason,
    )


def approve_request(*, request_record, approved_by, legal_basis):
    if not approved_by.has_perm("employees.manage_privacy_requests") and not approved_by.is_superuser:
        raise PermissionDenied("Privacy workflow permission is required.")
    if approved_by.pk == request_record.requested_by_id:
        raise PermissionDenied("Privacy requests require independent approval.")
    if not legal_basis.strip():
        raise ValidationError("Documented legal basis and retention analysis are required.")
    request_record.status = PrivacyRequestStatus.APPROVED
    request_record.approved_by = approved_by
    request_record.legal_basis = legal_basis
    request_record.save(update_fields=("status", "approved_by", "legal_basis"))
    return request_record


def _safe_model_dict(instance, excluded=()):
    if instance is None:
        return None
    return {
        key: str(value) if value is not None else None
        for key, value in model_to_dict(instance).items()
        if key not in excluded
    }


@transaction.atomic
def export_employee_data(*, request_record, actor, request=None):
    _authorize(request_record, actor)
    if request_record.request_type != PrivacyRequestType.EXPORT:
        raise ValidationError("Request type does not permit export.")
    employee = request_record.employee
    payload = {
        "employee": _safe_model_dict(employee, {"organization"}),
        "personal_information": _safe_model_dict(
            getattr(employee, "personal_information", None), {"organization", "employee"}
        ),
        "bank_accounts": [
            _safe_model_dict(row, {"organization", "employee", "account_fingerprint", "account_number_token"})
            for row in employee.bank_accounts.all()
        ],
        "tax_profiles": [
            _safe_model_dict(row, {"organization", "employee", "tax_identifier_fingerprint", "tax_identifier_token"})
            for row in employee.tax_profiles.all()
        ],
        "payroll_input_ids": list(EmployeePayrollInput.objects.filter(employee=employee).values_list("pk", flat=True)),
        "preservation_notice": "Payroll records and audit evidence may be retained where legally required.",
    }
    content = json.dumps(payload, sort_keys=True, indent=2).encode()
    _complete(request_record, actor, hashlib.sha256(content).hexdigest(), request)
    return content


@transaction.atomic
def correct_employee_data(*, request_record, actor, general_changes=None, personal_changes=None, request=None):
    _authorize(request_record, actor)
    if request_record.request_type != PrivacyRequestType.CORRECTION:
        raise ValidationError("Request type does not permit correction.")
    general_changes, personal_changes = general_changes or {}, personal_changes or {}
    if set(general_changes) - GENERAL_CORRECTION_FIELDS or set(personal_changes) - PERSONAL_CORRECTION_FIELDS:
        raise ValidationError("Correction contains a field that must use a specialized legal workflow.")
    employee = request_record.employee
    for field, value in general_changes.items():
        setattr(employee, field, value)
    employee.full_clean()
    employee.save(update_fields=(*general_changes.keys(), "updated_at"))
    if personal_changes:
        personal, _ = EmployeePersonalInformation.objects.get_or_create(
            employee=employee, defaults={"organization": employee.organization}
        )
        for field, value in personal_changes.items():
            setattr(personal, field, value)
        personal.full_clean()
        personal.save(update_fields=personal_changes.keys())
    _complete(request_record, actor, "", request)


@transaction.atomic
def delete_employee_data(*, request_record, actor, retention_until, request=None):
    """Minimize non-required PII while retaining protected payroll/tax evidence."""
    _authorize(request_record, actor)
    if request_record.request_type != PrivacyRequestType.DELETION:
        raise ValidationError("Request type does not permit deletion.")
    if retention_until < timezone.localdate():
        raise ValidationError("Retention date cannot be in the past.")
    employee = request_record.employee
    EmployeePersonalInformation.objects.filter(employee=employee).update(
        legal_name_encrypted="",
        date_of_birth_encrypted="",
        personal_email_encrypted="",
        personal_phone_encrypted="",
        residential_address_encrypted="",
        emergency_contact_encrypted="",
        government_id_token="",
        archived_at=timezone.now(),
        retention_until=retention_until,
    )
    EmployeeBankAccount.objects.filter(employee=employee).update(
        account_holder_encrypted="",
        account_number_token="",
        routing_details_encrypted="",
        archived_at=timezone.now(),
        retention_until=retention_until,
    )
    EmployeeTaxProfile.objects.filter(employee=employee).update(
        archived_at=timezone.now(), retention_until=retention_until
    )
    employee.preferred_name = ""
    employee.work_email = ""
    employee.work_phone = ""
    employee.archive(retention_until=retention_until)
    _complete(request_record, actor, "", request)


def _complete(request_record, actor, response_sha256, request):
    request_record.status = PrivacyRequestStatus.COMPLETED
    request_record.completed_at = timezone.now()
    request_record.response_sha256 = response_sha256
    request_record.save(update_fields=("status", "completed_at", "response_sha256"))
    record_event(
        organization=request_record.organization,
        actor=actor,
        action=AuditAction.EXPORT if request_record.request_type == PrivacyRequestType.EXPORT else AuditAction.REDACT,
        object_type=request_record._meta.label,
        object_id=request_record.pk,
        after={"request_type": request_record.request_type, "status": request_record.status},
        request=request,
        sensitive=True,
    )
