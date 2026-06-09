"""Canonical role groups and their explicit model permissions."""

from django.contrib.auth.models import Group, Permission

ROLE_PERMISSIONS = {
    "administrator": [
        "view_organization",
        "change_organization",
        "view_payrollrecord",
        "add_payrollrecord",
        "change_payrollrecord",
        "delete_payrollrecord",
        "operate_payroll",
        "approve_payroll",
        "mark_payroll_paid",
        "view_auditannotation",
        "annotate_audit",
        "view_employee_sensitive",
        "view_personal_information",
        "change_personal_information",
        "view_banking_information",
        "change_banking_information",
        "view_tax_information",
        "change_tax_information",
        "approve_compensation",
        "apply_compensation",
    ],
    "payroll_operator": [
        "view_organization",
        "view_payrollrecord",
        "add_payrollrecord",
        "change_payrollrecord",
        "operate_payroll",
        "mark_payroll_paid",
        "view_banking_information",
        "change_banking_information",
        "view_tax_information",
        "change_tax_information",
    ],
    "employee": ["view_organization", "view_payrollrecord"],
    "auditor": ["view_organization", "view_payrollrecord", "view_auditannotation", "annotate_audit"],
    "client": ["view_organization", "view_payrollrecord", "view_auditannotation"],
}


def ensure_role_groups(**kwargs):
    for role, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role)
        group.permissions.set(Permission.objects.filter(codename__in=codenames))
