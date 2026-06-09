"""Payroll calculation rules version 1.

This module is append-only in spirit: future rule changes belong in a new versioned
module so old runs remain reproducible from their snapshots.
"""

from decimal import ROUND_HALF_UP, Decimal

from apps.payroll.models import InputType, LineItemCategory

RULES_VERSION = "v1"
MONEY = Decimal("0.01")
RULES_SNAPSHOT = {
    "version": RULES_VERSION,
    "rounding": "ROUND_HALF_UP",
    "money_precision": "0.01",
    "base_salary_proration": "amount * worked_days / period_days",
    "overtime_default_multiplier": "1.5",
    "deductions_reduce_net_pay": True,
}


def money(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def calculate_input(item):
    """Return a signed line item dictionary from an immutable input dictionary."""
    input_type = item["input_type"]
    amount = Decimal(str(item.get("amount", "0")))
    quantity = Decimal(str(item.get("quantity", "1")))
    rate = Decimal(str(item.get("rate", "0")))
    metadata = item.get("metadata", {})
    formula = "amount"

    if input_type == InputType.BASE_SALARY:
        worked_days = Decimal(str(metadata.get("worked_days", metadata.get("period_days", 1))))
        period_days = Decimal(str(metadata.get("period_days", 1)))
        if period_days <= 0:
            raise ValueError("period_days must be positive")
        raw = amount * worked_days / period_days
        formula = "amount * worked_days / period_days"
    elif input_type == InputType.HOURLY:
        raw = rate * quantity
        formula = "rate * quantity"
    elif input_type == InputType.OVERTIME:
        multiplier = Decimal(str(metadata.get("multiplier", "1.5")))
        raw = rate * quantity * multiplier
        formula = "rate * quantity * multiplier"
    else:
        raw = amount

    category = LineItemCategory.EARNING
    signed_amount = money(raw)
    if input_type == InputType.BENEFIT:
        category = LineItemCategory.BENEFIT
    elif input_type == InputType.PRE_TAX_DEDUCTION:
        category = LineItemCategory.PRE_TAX_DEDUCTION
        signed_amount = -abs(signed_amount)
    elif input_type == InputType.POST_TAX_DEDUCTION:
        category = LineItemCategory.POST_TAX_DEDUCTION
        signed_amount = -abs(signed_amount)
    elif input_type == InputType.EMPLOYER_COST:
        category = LineItemCategory.EMPLOYER_COST

    return {
        "employee_id": item["employee_id"],
        "input_type": input_type,
        "category": category,
        "description": item.get("description") or InputType(input_type).label,
        "amount": signed_amount,
        "explanation": {"formula": formula, "unrounded_result": str(raw), "rounded_result": str(signed_amount)},
        "source_snapshot": item,
    }


def calculate(inputs):
    lines = [calculate_input(item) for item in inputs]
    gross = money(
        sum(
            (
                line["amount"]
                for line in lines
                if line["category"] in {LineItemCategory.EARNING, LineItemCategory.BENEFIT}
            ),
            Decimal("0"),
        )
    )
    pre_tax = money(
        -sum((line["amount"] for line in lines if line["category"] == LineItemCategory.PRE_TAX_DEDUCTION), Decimal("0"))
    )
    post_tax = money(
        -sum(
            (line["amount"] for line in lines if line["category"] == LineItemCategory.POST_TAX_DEDUCTION), Decimal("0")
        )
    )
    employer_costs = money(
        sum((line["amount"] for line in lines if line["category"] == LineItemCategory.EMPLOYER_COST), Decimal("0"))
    )
    net = money(gross - pre_tax - post_tax)
    return {
        "lines": lines,
        "gross_pay": gross,
        "pre_tax_deductions": pre_tax,
        "post_tax_deductions": post_tax,
        "employer_costs": employer_costs,
        "net_pay": net,
        "explanation": {"net_pay": "gross_pay - pre_tax_deductions - post_tax_deductions"},
    }
