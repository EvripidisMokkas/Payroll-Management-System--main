"""Validated, approval-gated tax table imports."""

import hashlib
import json
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.taxation.models import (
    Allowance,
    ContributionLimit,
    EmployerTax,
    FilingStatus,
    Jurisdiction,
    RuleStatus,
    TaxBracket,
    TaxRuleVersion,
    TaxYear,
)


def _validate_payload(payload):
    errors = []
    required = {"jurisdiction", "version", "effective_from", "brackets"}
    missing = sorted(required - payload.keys())
    if missing:
        errors.append(f"Missing required fields: {', '.join(missing)}")
    try:
        date.fromisoformat(payload.get("effective_from", ""))
    except ValueError:
        errors.append("effective_from must be an ISO date")
    previous_upper = Decimal("0")
    for index, bracket in enumerate(payload.get("brackets", [])):
        try:
            lower = Decimal(str(bracket["lower_bound"]))
            upper = Decimal(str(bracket["upper_bound"])) if bracket.get("upper_bound") is not None else None
            rate = Decimal(str(bracket["rate"]))
            if lower < previous_upper or rate < 0 or (upper is not None and upper <= lower):
                errors.append(f"Bracket {index} has overlapping bounds, invalid bounds, or a negative rate")
            if upper is not None:
                previous_upper = upper
        except (KeyError, ValueError, ArithmeticError):
            errors.append(f"Bracket {index} contains invalid numeric values")
    return errors


@transaction.atomic
def import_tax_table(payload, *, source=""):
    errors = _validate_payload(payload)
    jurisdiction = Jurisdiction.objects.get(code=payload["jurisdiction"])
    rule = TaxRuleVersion.objects.create(
        jurisdiction=jurisdiction,
        version=payload["version"],
        effective_from=payload.get("effective_from", date.today().isoformat()),
        effective_to=payload.get("effective_to"),
        source=source,
        source_checksum=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        imported_payload=payload,
        validation_errors=errors,
        status=RuleStatus.DRAFT if errors else RuleStatus.VALIDATED,
    )
    statuses = {}
    for item in payload.get("filing_statuses", []):
        statuses[item["code"]] = FilingStatus.objects.create(rule_version=rule, **item)
    if not errors:
        TaxBracket.objects.bulk_create(
            [
                TaxBracket(
                    rule_version=rule,
                    filing_status=statuses.get(item.get("filing_status")),
                    lower_bound=item["lower_bound"],
                    upper_bound=item.get("upper_bound"),
                    rate=item["rate"],
                    fixed_amount=item.get("fixed_amount", 0),
                )
                for item in payload["brackets"]
            ]
        )
        TaxYear.objects.bulk_create([TaxYear(rule_version=rule, **item) for item in payload.get("tax_years", [])])
        Allowance.objects.bulk_create(
            [
                Allowance(
                    rule_version=rule,
                    filing_status=statuses.get(item.get("filing_status")),
                    code=item["code"],
                    amount=item["amount"],
                    metadata=item.get("metadata", {}),
                )
                for item in payload.get("allowances", [])
            ]
        )
        ContributionLimit.objects.bulk_create(
            [ContributionLimit(rule_version=rule, **item) for item in payload.get("contribution_limits", [])]
        )
        EmployerTax.objects.bulk_create(
            [EmployerTax(rule_version=rule, **item) for item in payload.get("employer_taxes", [])]
        )
    return rule


def approve_rule(rule, *, actor):
    if rule.status != RuleStatus.VALIDATED or rule.validation_errors:
        raise ValidationError("Only successfully validated tax rules can be approved.")
    rule.status = RuleStatus.APPROVED
    rule.approved_by = actor
    rule.approved_at = timezone.now()
    rule.save(update_fields=("status", "approved_by", "approved_at"))
    return rule


@transaction.atomic
def activate_rule(rule):
    if rule.status != RuleStatus.APPROVED:
        raise ValidationError("Tax rules require approval before activation.")
    TaxRuleVersion.objects.filter(
        jurisdiction=rule.jurisdiction, status=RuleStatus.ACTIVE, effective_from=rule.effective_from
    ).update(status=RuleStatus.RETIRED)
    rule.status = RuleStatus.ACTIVE
    rule.activated_at = timezone.now()
    rule.save(update_fields=("status", "activated_at"))
    return rule
