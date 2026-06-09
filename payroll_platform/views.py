"""Platform-level views."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.forms import modelform_factory
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from apps.clients.models import Client
from apps.auditing.models import AuditAction, AuditEvent
from apps.employees.models import Employee, EmploymentStatus
from apps.organizations.models import Organization, OrganizationMembership
from apps.organizations.services import ROLE_ACTIONS, assign_membership, authorize
from apps.payroll.models import PayrollLifecycle, PayrollPeriod
from payroll_platform.workspace import DOMAINS


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "home.html")


@login_required
def dashboard(request):
    organizations = Organization.objects.all()
    employees = Employee.objects.for_user(request.user)
    clients = Client.objects.for_user(request.user)
    periods = PayrollPeriod.objects.for_user(request.user)

    if not request.user.is_superuser:
        organizations = organizations.filter(
            memberships__user=request.user,
            memberships__is_active=True,
        ).distinct()

    recent_periods = periods.select_related("organization", "schedule").order_by("-pay_date")[:5]
    active_employees = employees.filter(status=EmploymentStatus.ACTIVE).count()
    total_employees = employees.count()

    context = _workspace_context(request)
    context.update(
        {
            "organization_count": organizations.count(),
            "employee_count": total_employees,
            "active_employee_count": active_employees,
            "client_count": clients.count(),
            "payroll_count": periods.count(),
            "open_payroll_count": periods.exclude(
                status__in=[PayrollLifecycle.PAID, PayrollLifecycle.ARCHIVED]
            ).count(),
            "recent_periods": recent_periods,
        }
    )
    return render(request, "dashboard.html", context)


def _organizations_for(user):
    if user.is_superuser:
        return Organization.objects.filter(is_active=True)
    return Organization.objects.filter(
        memberships__user=user, memberships__is_active=True, is_active=True
    ).distinct()


def _workspace_context(request, selected_organization=None):
    organizations = _organizations_for(request.user)
    memberships = {
        membership.organization_id: membership
        for membership in OrganizationMembership.objects.filter(
            user=request.user, is_active=True, organization__in=organizations
        )
    }
    actions = set().union(*(ROLE_ACTIONS[m.role] for m in memberships.values())) if memberships else set()
    if request.user.is_superuser:
        actions = set().union(*ROLE_ACTIONS.values())
    visible_domains = [domain for domain in DOMAINS.values() if domain.read_action in actions]
    return {
        "workspace_domains": visible_domains,
        "workspace_organizations": organizations,
        "selected_organization": selected_organization,
        "workspace_actions": actions,
    }


def _selected_organization(request, required_action):
    organizations = _organizations_for(request.user)
    organization_id = request.GET.get("organization") or request.POST.get("organization")
    organization = get_object_or_404(organizations, pk=organization_id) if organization_id else organizations.first()
    if organization is None:
        raise PermissionDenied("You do not have access to an active organization.")
    authorize(request.user, organization, required_action)
    return organization


def _domain_queryset(domain, request, organization):
    if domain.slug == "access":
        return OrganizationMembership.objects.filter(organization=organization).select_related("user", "organization")
    return domain.model.objects.for_user(request.user).filter(organization=organization)


def _display_value(record, field_name):
    field = record._meta.get_field(field_name)
    display_method = getattr(record, f"get_{field_name}_display", None)
    value = display_method() if display_method else getattr(record, field_name)
    if value in (None, ""):
        return "—"
    if field.is_relation and value:
        return str(value)
    if hasattr(value, "strftime"):
        return value.strftime("%b %d, %Y")
    return value


@login_required
def workspace_domain(request, domain_slug):
    domain = DOMAINS.get(domain_slug)
    if domain is None:
        raise Http404
    organization = _selected_organization(request, domain.read_action)
    records = _domain_queryset(domain, request, organization).order_by("-pk")[:100]
    rows = [(record, [_display_value(record, column) for column in domain.columns]) for record in records]
    context = _workspace_context(request, organization)
    context.update({"domain": domain, "columns": domain.columns, "rows": rows, "can_write": bool(domain.write_action and (request.user.is_superuser or domain.write_action in context["workspace_actions"]))})
    return render(request, "workspace/domain.html", context)


@login_required
def workspace_record_form(request, domain_slug, record_id=None):
    domain = DOMAINS.get(domain_slug)
    if domain is None:
        raise Http404
    if not domain.write_action:
        raise PermissionDenied("This workspace area is read-only.")
    organization = _selected_organization(request, domain.write_action)
    instance = None
    if record_id:
        instance = get_object_or_404(_domain_queryset(domain, request, organization), pk=record_id)
    Form = modelform_factory(domain.model, fields=domain.fields)
    form = Form(request.POST or None, instance=instance)
    for field in form.fields.values():
        queryset = getattr(field, "queryset", None)
        if queryset is not None and hasattr(queryset.model, "organization_id"):
            field.queryset = queryset.filter(organization=organization)
    if request.method == "POST" and form.is_valid():
        is_new = instance is None
        record = form.save(commit=False)
        record.organization = organization
        if domain.slug == "access":
            assign_membership(request.user, record.user, organization, record.role)
            AuditEvent.objects.create(
                organization=organization,
                actor=request.user,
                action=AuditAction.UPDATE,
                object_type="organization_membership",
                object_id=str(record.user_id),
                object_label=str(record.user),
                after_summary={"role": record.role, "active": record.is_active},
            )
            return redirect(f"/workspace/{domain.slug}/?organization={organization.pk}")
        if hasattr(record, "owner_id") and not record.owner_id:
            record.owner = request.user
        if hasattr(record, "author_id") and not record.author_id:
            record.author = request.user
        record.full_clean()
        record.save()
        form.save_m2m()
        AuditEvent.objects.create(
            organization=organization,
            actor=request.user,
            action=AuditAction.CREATE if is_new else AuditAction.UPDATE,
            object_type=record._meta.label_lower,
            object_id=str(record.pk),
            object_label=str(record),
            after_summary={"browser_workspace": True},
        )
        return redirect(f"/workspace/{domain.slug}/?organization={organization.pk}")
    context = _workspace_context(request, organization)
    context.update({"domain": domain, "form": form, "record": instance})
    return render(request, "workspace/form.html", context)


@never_cache
def health_check(request):
    return JsonResponse({"status": "ok"})
