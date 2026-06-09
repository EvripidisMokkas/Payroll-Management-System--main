"""Transactional payroll processing, lifecycle, and correction orchestration."""

from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.organizations.models import OrganizationMembership, OrganizationRole
from apps.payroll.models import (
    PROTECTED_PERIOD_STATUSES,
    CalculationRun,
    EmployeePayrollInput,
    PayrollApproval,
    PayrollCorrection,
    PayrollLifecycle,
    PayrollLineItem,
    PayrollPeriod,
    Payslip,
)
from apps.security.legal import require_approved_jurisdiction
from apps.taxation.models import Jurisdiction, OrganizationTaxConfiguration
from apps.taxation.services.engine import active_rule_for
from apps.taxation.services.engine import registry as tax_registry

from . import v1

CALCULATORS = {v1.RULES_VERSION: v1}
ALLOWED_TRANSITIONS = {
    PayrollLifecycle.DRAFT: {
        PayrollLifecycle.VALIDATION: {OrganizationRole.PAYROLL_OPERATOR, OrganizationRole.ADMINISTRATOR}
    },
    PayrollLifecycle.VALIDATION: {PayrollLifecycle.APPROVAL: {OrganizationRole.ADMINISTRATOR}},
    PayrollLifecycle.APPROVAL: {PayrollLifecycle.LOCKED: {OrganizationRole.ADMINISTRATOR}},
    PayrollLifecycle.LOCKED: {
        PayrollLifecycle.PAID: {OrganizationRole.PAYROLL_OPERATOR, OrganizationRole.ADMINISTRATOR}
    },
    PayrollLifecycle.PAID: {PayrollLifecycle.CORRECTED: {OrganizationRole.ADMINISTRATOR}},
    PayrollLifecycle.CORRECTED: {PayrollLifecycle.ARCHIVED: {OrganizationRole.ADMINISTRATOR}},
}


def _role_for(actor, organization):
    if actor.is_superuser:
        return OrganizationRole.ADMINISTRATOR
    membership = OrganizationMembership.objects.filter(user=actor, organization=organization, is_active=True).first()
    if not membership:
        raise PermissionDenied("An active organization membership is required.")
    return membership.role


def _input_snapshot(period):
    return [
        {
            "id": row.id,
            "employee_id": row.employee_id,
            "input_type": row.input_type,
            "description": row.description,
            "amount": str(row.amount),
            "quantity": str(row.quantity),
            "rate": str(row.rate),
            "source_key": row.source_key,
            "metadata": row.metadata,
        }
        for row in EmployeePayrollInput.objects.filter(period=period).order_by("employee_id", "id")
    ]


def _tax_provenance(period, jurisdiction_code=None):
    configurations = OrganizationTaxConfiguration.objects.filter(organization=period.organization, active=True)
    if jurisdiction_code:
        try:
            jurisdiction = Jurisdiction.objects.get(code=jurisdiction_code)
        except Jurisdiction.DoesNotExist as exc:
            raise ValidationError(f"Unknown tax jurisdiction: {jurisdiction_code}.") from exc
        if not configurations.filter(jurisdiction=jurisdiction).exists():
            raise ValidationError(f"Jurisdiction {jurisdiction_code} is not configured for this organization.")
    else:
        required = list(configurations.filter(required=True).select_related("jurisdiction"))
        if not required:
            return "not_applicable", "not_applicable"
        if len(required) > 1:
            raise ValidationError("Multiple required tax jurisdictions are configured; specify jurisdiction_code.")
        jurisdiction = required[0].jurisdiction
    rule = active_rule_for(jurisdiction, period.pay_date)
    tax_registry.resolve(jurisdiction)
    return jurisdiction.code, rule.version


def _create_run(*, period, inputs, rules_version, idempotency_key, actor, adjustment_of=None, jurisdiction_code=None):
    require_approved_jurisdiction(period.organization.jurisdiction, "payroll")
    calculator = CALCULATORS.get(rules_version)
    if not calculator:
        raise ValidationError(f"Unknown payroll rules version: {rules_version}")
    tax_jurisdiction_code, tax_rule_version = _tax_provenance(period, jurisdiction_code)
    result = calculator.calculate(inputs)
    run = CalculationRun.objects.create(
        organization=period.organization,
        period=period,
        adjustment_of=adjustment_of,
        rules_version=rules_version,
        tax_jurisdiction_code=tax_jurisdiction_code,
        tax_rule_version=tax_rule_version,
        idempotency_key=idempotency_key,
        input_snapshot=inputs,
        rules_snapshot={
            **calculator.RULES_SNAPSHOT,
            "taxation": {"jurisdiction": tax_jurisdiction_code, "version": tax_rule_version},
        },
        explanation=result["explanation"],
        gross_pay=result["gross_pay"],
        pre_tax_deductions=result["pre_tax_deductions"],
        post_tax_deductions=result["post_tax_deductions"],
        employer_costs=result["employer_costs"],
        net_pay=result["net_pay"],
        created_by=actor,
    )
    PayrollLineItem.objects.bulk_create(
        [
            PayrollLineItem(
                organization=period.organization,
                run=run,
                employee_id=line["employee_id"],
                input_type=line["input_type"],
                category=line["category"],
                description=line["description"],
                amount=line["amount"],
                explanation=line["explanation"],
                source_snapshot=line["source_snapshot"],
            )
            for line in result["lines"]
        ]
    )
    _create_payslips(run, result["lines"])
    return run


def _create_payslips(run, lines):
    by_employee = defaultdict(list)
    for line in lines:
        by_employee[line["employee_id"]].append(line)
    payslips = []
    for employee_id, employee_lines in by_employee.items():
        gross = v1.money(
            sum((line["amount"] for line in employee_lines if line["category"] in {"earning", "benefit"}), Decimal("0"))
        )
        deductions = v1.money(
            -sum(
                (
                    line["amount"]
                    for line in employee_lines
                    if line["category"] in {"pre_tax_deduction", "post_tax_deduction"}
                ),
                Decimal("0"),
            )
        )
        serializable_lines = [{**line, "amount": str(line["amount"])} for line in employee_lines]
        payslips.append(
            Payslip(
                organization=run.organization,
                run=run,
                employee_id=employee_id,
                gross_pay=gross,
                net_pay=v1.money(gross - deductions),
                snapshot={"rules_version": run.rules_version, "lines": serializable_lines},
            )
        )
    Payslip.objects.bulk_create(payslips)


def process_payroll(*, period, idempotency_key, actor=None, rules_version=v1.RULES_VERSION, jurisdiction_code=None):
    """Calculate a regular run exactly once for an idempotency key."""
    existing = CalculationRun.objects.filter(organization=period.organization, idempotency_key=idempotency_key).first()
    if existing:
        return existing
    with transaction.atomic():
        period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
        if period.status in PROTECTED_PERIOD_STATUSES:
            raise ValidationError("Locked or paid periods cannot be processed; create an adjustment run instead.")
        inputs = _input_snapshot(period)
        try:
            with transaction.atomic():
                return _create_run(
                    period=period,
                    inputs=inputs,
                    rules_version=rules_version,
                    idempotency_key=idempotency_key,
                    actor=actor,
                    jurisdiction_code=jurisdiction_code,
                )
        except IntegrityError:
            return CalculationRun.objects.get(organization=period.organization, idempotency_key=idempotency_key)


def create_adjustment_run(
    *, original_period, inputs, reason, idempotency_key, actor, rules_version=v1.RULES_VERSION, jurisdiction_code=None
):
    """Record signed correction inputs without mutating the original locked/paid evidence."""
    if original_period.status not in {PayrollLifecycle.LOCKED, PayrollLifecycle.PAID, PayrollLifecycle.CORRECTED}:
        raise ValidationError("Adjustments require a locked, paid, or corrected original period.")
    if _role_for(actor, original_period.organization) != OrganizationRole.ADMINISTRATOR:
        raise PermissionDenied("Only organization administrators can create payroll adjustments.")
    existing = CalculationRun.objects.filter(
        organization=original_period.organization, idempotency_key=idempotency_key
    ).first()
    if existing:
        return existing
    serialized = []
    for item in inputs:
        copied = dict(item)
        copied["amount"] = str(copied.get("amount", 0))
        copied["quantity"] = str(copied.get("quantity", 1))
        copied["rate"] = str(copied.get("rate", 0))
        copied.setdefault("metadata", {})
        copied.setdefault("description", "Correction adjustment")
        serialized.append(copied)
    with transaction.atomic():
        latest = original_period.calculation_runs.order_by("-created_at").first()
        run = _create_run(
            period=original_period,
            inputs=serialized,
            rules_version=rules_version,
            idempotency_key=idempotency_key,
            actor=actor,
            adjustment_of=latest,
            jurisdiction_code=jurisdiction_code,
        )
        PayrollCorrection.objects.create(
            organization=original_period.organization,
            original_period=original_period,
            adjustment_run=run,
            reason=reason,
            requested_by=actor,
        )
        return run


def transition_period(*, period, to_status, actor, explanation=""):
    """Apply an authorized lifecycle transition and retain its immutable approval evidence."""
    with transaction.atomic():
        period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
        role = _role_for(actor, period.organization)
        permitted_roles = ALLOWED_TRANSITIONS.get(period.status, {}).get(to_status, set())
        if role not in permitted_roles:
            raise PermissionDenied(f"Role {role} cannot transition payroll from {period.status} to {to_status}.")
        if to_status in {PayrollLifecycle.APPROVAL, PayrollLifecycle.LOCKED} and not period.calculation_runs.exists():
            raise ValidationError("Payroll must have a calculation run before approval or locking.")
        previous = period.status
        timestamps = {}
        if to_status == PayrollLifecycle.LOCKED:
            timestamps["locked_at"] = timezone.now()
        elif to_status == PayrollLifecycle.PAID:
            timestamps["paid_at"] = timezone.now()
        elif to_status == PayrollLifecycle.ARCHIVED:
            timestamps["archived_at"] = timezone.now()
        PayrollPeriod.objects.filter(pk=period.pk).update(status=to_status, **timestamps)
        PayrollApproval.objects.create(
            organization=period.organization,
            period=period,
            from_status=previous,
            to_status=to_status,
            actor=actor,
            actor_role=role,
            explanation=explanation,
            snapshot={"period_id": period.pk, "from_status": previous, "to_status": to_status},
        )
        period.refresh_from_db()
        return period
