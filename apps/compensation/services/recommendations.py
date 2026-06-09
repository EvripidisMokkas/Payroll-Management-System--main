"""Deterministic compensation recommendation, approval, and application workflow."""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from apps.employees.models import Salary
from apps.organizations.services import authorize, membership_for

from ..models import (
    ApprovalAction,
    CompensationApproval,
    CompensationPolicy,
    CompensationRecommendation,
    RecommendationStatus,
    ScoringRule,
)

MONEY = Decimal("0.01")
SCORE = Decimal("0.0001")


def _decimal(value):
    return Decimal(str(value))


def _money(value):
    return _decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def policy_as_of(*, organization, name, as_of_date):
    """Return the latest active policy version effective on a date."""
    return (
        CompensationPolicy.objects.filter(
            organization=organization,
            name=name,
            is_active=True,
            archived_at__isnull=True,
            effective_from__lte=as_of_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))
        .order_by("-effective_from", "-pk")
        .first()
    )


def _rules_as_of(policy, as_of_date):
    rules = (
        ScoringRule.objects.filter(
            policy=policy,
            archived_at__isnull=True,
            effective_from__lte=as_of_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))
        .order_by("criterion", "-effective_from", "-pk")
    )
    selected = {}
    for rule in rules:
        selected.setdefault(rule.criterion, rule)
    return [selected[key] for key in sorted(selected)]


def _current_salary(employee, as_of_date):
    return (
        Salary.as_of(as_of_date)
        .filter(employee=employee, archived_at__isnull=True)
        .order_by("-effective_from", "-pk")
        .first()
    )


def create_recommendation(*, employee, policy, as_of_date, source_data, actor=None, pay_equity_reviewed=False):
    """Create an auditable recommendation without changing employee compensation."""
    if policy.organization_id != employee.organization_id:
        raise ValidationError("Policy and employee must belong to the same organization.")
    if not (
        policy.is_active
        and policy.archived_at is None
        and policy.effective_from <= as_of_date
        and (policy.effective_to is None or policy.effective_to >= as_of_date)
    ):
        raise ValidationError("The selected compensation policy is not effective on the recommendation date.")

    prohibited_used = sorted(set(policy.prohibited_criteria or []).intersection(source_data))
    if prohibited_used:
        raise ValidationError("Prohibited source-data criteria supplied: " + ", ".join(prohibited_used))

    rules = _rules_as_of(policy, as_of_date)
    if not rules:
        raise ValidationError("The policy has no scoring rules effective on the recommendation date.")
    missing = [rule.criterion for rule in rules if rule.criterion not in source_data]
    if missing:
        raise ValidationError("Missing source data for criteria: " + ", ".join(missing))

    total_weight = sum((rule.weight for rule in rules), Decimal("0"))
    if total_weight <= 0:
        raise ValidationError("Effective scoring-rule weights must total more than zero.")

    weighted_total = Decimal("0")
    breakdown = {}
    rule_snapshots = []
    for rule in rules:
        raw = _decimal(source_data[rule.criterion])
        span = rule.threshold_max - rule.threshold_min
        normalized = Decimal("1") if span == 0 and raw >= rule.threshold_max else Decimal("0")
        if span > 0:
            normalized = (raw - rule.threshold_min) / span
        normalized = max(Decimal("0"), min(Decimal("1"), normalized))
        weighted = normalized * rule.weight
        weighted_total += weighted
        breakdown[rule.criterion] = {
            "raw_value": str(raw),
            "threshold_min": str(rule.threshold_min),
            "threshold_max": str(rule.threshold_max),
            "target_value": str(rule.target_value),
            "normalized_score": str((normalized * 100).quantize(SCORE, rounding=ROUND_HALF_UP)),
            "weight": str(rule.weight),
            "weighted_points": str((weighted / total_weight * 100).quantize(SCORE, rounding=ROUND_HALF_UP)),
            "rule_id": rule.pk,
        }
        rule_snapshots.append(
            {
                "id": rule.pk,
                "criterion": rule.criterion,
                "weight": str(rule.weight),
                "threshold_min": str(rule.threshold_min),
                "threshold_max": str(rule.threshold_max),
                "target_value": str(rule.target_value),
                "effective_from": rule.effective_from.isoformat(),
                "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
                "metadata": _json_value(rule.metadata),
            }
        )

    score = (weighted_total / total_weight * 100).quantize(SCORE, rounding=ROUND_HALF_UP)
    current_salary = _current_salary(employee, as_of_date)
    if not current_salary:
        raise ValidationError("Employee has no salary effective on the recommendation date.")
    if current_salary.currency != policy.currency:
        raise ValidationError("Employee salary and policy currencies must match.")

    adjustment_percent = policy.minimum_adjustment_percent + (
        (policy.maximum_adjustment_percent - policy.minimum_adjustment_percent) * score / Decimal("100")
    )
    midpoint = _money(current_salary.amount * (Decimal("1") + adjustment_percent))
    adjustment = _money(midpoint - current_salary.amount)
    proposed_min = _money(current_salary.amount * (Decimal("1") + policy.minimum_adjustment_percent))
    proposed_max = _money(current_salary.amount * (Decimal("1") + policy.maximum_adjustment_percent))

    deviation = abs(_decimal(source_data.get("pay_equity_deviation_percent", "0")))
    controls = {
        "adjustment_within_bounds": proposed_min <= midpoint <= proposed_max,
        "budget_within_limit": policy.budget_remaining is None or adjustment <= policy.budget_remaining,
        "pay_equity_within_limit": deviation <= policy.pay_equity_max_deviation_percent,
        "pay_equity_deviation_percent": str(deviation),
        "prohibited_criteria_checked": True,
    }
    explanation = (
        f"Policy {policy.name} {policy.version} produced a score of {score} from {len(rules)} effective-dated "
        f"criteria. The proposed midpoint is {policy.currency} {midpoint}, an adjustment of {policy.currency} "
        f"{adjustment}, bounded by {policy.currency} {proposed_min} and {policy.currency} {proposed_max}. "
        "No salary change occurs until an authorized human approves and applies this recommendation."
    )
    policy_snapshot = {
        "id": policy.pk,
        "name": policy.name,
        "version": policy.version,
        "effective_from": policy.effective_from.isoformat(),
        "effective_to": policy.effective_to.isoformat() if policy.effective_to else None,
        "minimum_adjustment_percent": str(policy.minimum_adjustment_percent),
        "maximum_adjustment_percent": str(policy.maximum_adjustment_percent),
        "budget_limit": str(policy.budget_limit),
        "budget_committed": str(policy.budget_committed),
        "require_pay_equity_review": policy.require_pay_equity_review,
        "pay_equity_max_deviation_percent": str(policy.pay_equity_max_deviation_percent),
        "prohibited_criteria": list(policy.prohibited_criteria),
        "rules": rule_snapshots,
    }
    return CompensationRecommendation.objects.create(
        organization=employee.organization,
        policy=policy,
        employee=employee,
        current_salary=current_salary,
        as_of_date=as_of_date,
        score=score,
        score_breakdown=breakdown,
        source_data_snapshot=_json_value(source_data),
        policy_snapshot=policy_snapshot,
        proposed_min=proposed_min,
        proposed_midpoint=midpoint,
        proposed_max=proposed_max,
        proposed_adjustment=adjustment,
        currency=policy.currency,
        explanation=explanation,
        controls=controls,
        pay_equity_reviewed=pay_equity_reviewed,
        created_by=actor,
    )


def _authorized_role(actor, organization, action):
    authorize(actor, organization, action)
    membership = membership_for(actor, organization)
    return "superuser" if membership is None else membership.role


@transaction.atomic
def approve_recommendation(*, recommendation, actor, explanation=""):
    """Record authorized human approval after rechecking every policy control."""
    recommendation = (
        CompensationRecommendation.objects.select_for_update().select_related("policy").get(pk=recommendation.pk)
    )
    actor_role = _authorized_role(actor, recommendation.organization, "compensation.approve")
    if recommendation.status != RecommendationStatus.PENDING_APPROVAL:
        raise ValidationError("Only pending recommendations can be approved.")
    if recommendation.created_by_id == actor.pk:
        raise PermissionDenied("Recommendation creators cannot approve their own recommendation.")
    if recommendation.policy.require_pay_equity_review and not recommendation.pay_equity_reviewed:
        raise ValidationError("The required pay-equity review has not been completed.")
    failed_controls = sorted(
        key for key, passed in recommendation.controls.items() if key.endswith("_limit") and not passed
    )
    if failed_controls or not recommendation.controls.get("adjustment_within_bounds", False):
        raise ValidationError("Recommendation failed controls: " + ", ".join(failed_controls or ["adjustment bounds"]))
    if (
        recommendation.policy.budget_remaining is not None
        and recommendation.proposed_adjustment > recommendation.policy.budget_remaining
    ):
        raise ValidationError("The recommendation exceeds the policy's remaining budget.")

    CompensationApproval.objects.create(
        organization=recommendation.organization,
        recommendation=recommendation,
        action=ApprovalAction.APPROVED,
        actor=actor,
        actor_role=actor_role,
        explanation=explanation,
        snapshot={"status": recommendation.status, "controls": recommendation.controls},
    )
    recommendation.status = RecommendationStatus.APPROVED
    recommendation.save(update_fields=("status",))
    return recommendation


@transaction.atomic
def apply_approved_recommendation(*, recommendation, actor, effective_from, explanation=""):
    """Apply an approved recommendation to salary; unapproved recommendations can never change salary."""
    recommendation = (
        CompensationRecommendation.objects.select_for_update()
        .select_related("policy", "employee", "current_salary")
        .get(pk=recommendation.pk)
    )
    actor_role = _authorized_role(actor, recommendation.organization, "compensation.apply")
    if (
        recommendation.status != RecommendationStatus.APPROVED
        or not recommendation.approvals.filter(action=ApprovalAction.APPROVED).exists()
    ):
        raise PermissionDenied("An authorized human approval is required before changing compensation.")
    if effective_from <= recommendation.as_of_date:
        raise ValidationError("The compensation change must take effect after the recommendation date.")

    current = recommendation.current_salary
    if current.effective_to is None or current.effective_to >= effective_from:
        current.effective_to = effective_from - timedelta(days=1)
        current.save(update_fields=("effective_to",))
    salary = Salary.objects.create(
        organization=recommendation.organization,
        employee=recommendation.employee,
        amount=recommendation.proposed_midpoint,
        currency=recommendation.currency,
        frequency=current.frequency,
        effective_from=effective_from,
    )
    policy = CompensationPolicy.objects.select_for_update().get(pk=recommendation.policy_id)
    policy.budget_committed += recommendation.proposed_adjustment
    policy.full_clean()
    policy.save(update_fields=("budget_committed",))

    CompensationApproval.objects.create(
        organization=recommendation.organization,
        recommendation=recommendation,
        action=ApprovalAction.APPLIED,
        actor=actor,
        actor_role=actor_role,
        explanation=explanation,
        snapshot={"salary_id": salary.pk, "amount": str(salary.amount), "effective_from": effective_from.isoformat()},
    )
    recommendation.status = RecommendationStatus.APPLIED
    recommendation.resulting_salary = salary
    recommendation.save(update_fields=("status", "resulting_salary"))
    return salary
