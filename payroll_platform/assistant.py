"""RBAC-aware Ollama assistant with a deliberately small operation allowlist."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.utils.dateparse import parse_date

from apps.auditing.models import AuditAction, AuditAnnotation, AuditEvent
from apps.organizations.models import Organization
from apps.organizations.services import ROLE_ACTIONS, authorize, membership_for
from apps.risk.models import RiskRegisterEntry
from payroll_platform.workspace import DOMAINS


@dataclass(frozen=True)
class AssistantTool:
    name: str
    description: str
    action: str | None
    write: bool = False


TOOLS = {
    "workspace_summary": AssistantTool(
        "workspace_summary", "Count records in the workspace areas the user may read.", None
    ),
    "list_records": AssistantTool(
        "list_records", "List recent records from an authorized workspace area.", None
    ),
    "create_audit_note": AssistantTool(
        "create_audit_note", "Add an append-only audit note.", "audit.annotate", write=True
    ),
    "create_risk_entry": AssistantTool(
        "create_risk_entry", "Create an operational risk-register entry.", "risk.manage", write=True
    ),
}


def _organization_for(user, organization_id):
    organization = Organization.objects.filter(pk=organization_id, is_active=True).first()
    if organization is None:
        raise PermissionDenied("Select an active organization.")
    if not user.is_superuser and membership_for(user, organization) is None:
        raise PermissionDenied("You do not have access to this organization.")
    return organization


def _actions_for(user, organization):
    if user.is_superuser:
        return set().union(*ROLE_ACTIONS.values())
    membership = membership_for(user, organization)
    return ROLE_ACTIONS[membership.role] if membership else set()


def _serialize_record(domain, record):
    result = {"id": record.pk, "label": str(record)}
    for field_name in domain.columns[:5]:
        value = getattr(record, field_name, None)
        display = getattr(record, f"get_{field_name}_display", None)
        result[field_name] = str(display() if display else value)
    return result


def execute_tool(user, organization, name, arguments):
    tool = TOOLS.get(name)
    if tool is None:
        raise ValueError("Unsupported assistant operation.")
    if tool.action:
        authorize(user, organization, tool.action)

    if name == "workspace_summary":
        actions = _actions_for(user, organization)
        summary = {}
        for domain in DOMAINS.values():
            if domain.read_action not in actions:
                continue
            queryset = domain.model.objects.filter(organization=organization)
            if hasattr(queryset, "for_user"):
                queryset = domain.model.objects.for_user(user).filter(organization=organization)
            summary[domain.label] = queryset.count()
        return {"organization": organization.name, "record_counts": summary}

    if name == "list_records":
        domain = DOMAINS.get(str(arguments.get("domain", "")).lower())
        if domain is None:
            raise ValueError("Unknown workspace area.")
        authorize(user, organization, domain.read_action)
        limit = min(max(int(arguments.get("limit", 5)), 1), 20)
        if domain.slug == "access":
            queryset = domain.model.objects.filter(organization=organization).select_related("user")
        else:
            queryset = domain.model.objects.for_user(user).filter(organization=organization)
        return {
            "area": domain.label,
            "records": [_serialize_record(domain, record) for record in queryset.order_by("-pk")[:limit]],
        }

    if name == "create_audit_note":
        note = str(arguments.get("note", "")).strip()
        if not note:
            raise ValueError("The audit note cannot be empty.")
        annotation = AuditAnnotation.objects.create(organization=organization, author=user, note=note)
        AuditEvent.objects.create(
            organization=organization,
            actor=user,
            action=AuditAction.CREATE,
            object_type="auditing.auditannotation",
            object_id=str(annotation.pk),
            object_label="Assistant-created audit note",
            after_summary={"assistant_operation": True},
        )
        return {"created": True, "id": annotation.pk, "note": annotation.note}

    if name == "create_risk_entry":
        review_date = parse_date(str(arguments.get("review_date", "")))
        if review_date is None:
            raise ValueError("Review date must use YYYY-MM-DD format.")
        risk = RiskRegisterEntry(
            organization=organization,
            owner=user,
            title=str(arguments.get("title", "")).strip(),
            description=str(arguments.get("description", "")).strip(),
            likelihood=int(arguments.get("likelihood", 0)),
            impact=int(arguments.get("impact", 0)),
            mitigation=str(arguments.get("mitigation", "")).strip(),
            review_date=review_date,
        )
        risk.full_clean()
        risk.save()
        AuditEvent.objects.create(
            organization=organization,
            actor=user,
            action=AuditAction.CREATE,
            object_type=risk._meta.label_lower,
            object_id=str(risk.pk),
            object_label=risk.title,
            after_summary={"assistant_operation": True, "score": risk.score},
        )
        return {"created": True, "id": risk.pk, "title": risk.title, "score": risk.score}

    raise ValueError("Unsupported assistant operation.")


def _tool_schema(tool):
    properties = {}
    required = []
    if tool.name == "list_records":
        properties = {
            "domain": {"type": "string", "description": "Workspace slug such as employees, payroll, or risk"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        }
        required = ["domain"]
    elif tool.name == "create_audit_note":
        properties = {"note": {"type": "string", "description": "The exact note to append"}}
        required = ["note"]
    elif tool.name == "create_risk_entry":
        properties = {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "likelihood": {"type": "integer", "minimum": 1, "maximum": 5},
            "impact": {"type": "integer", "minimum": 1, "maximum": 5},
            "mitigation": {"type": "string"},
            "review_date": {"type": "string", "description": "Review date in YYYY-MM-DD format"},
        }
        required = list(properties)
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def _available_tools(user, organization):
    actions = _actions_for(user, organization)
    return [tool for tool in TOOLS.values() if tool.action is None or tool.action in actions]


def _ollama_chat(messages, tools):
    payload = json.dumps(
        {"model": settings.OLLAMA_MODEL, "messages": messages, "tools": [_tool_schema(tool) for tool in tools], "stream": False}
    ).encode()
    request = Request(
        f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=settings.OLLAMA_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode())


def _format_tool_results(results):
    sections = []
    for item in results:
        result = item["result"]
        if item["operation"] == "workspace_summary":
            counts = ", ".join(f"{label}: {count}" for label, count in result["record_counts"].items())
            sections.append(f"{result['organization']} workspace summary: {counts or 'no accessible records'}.")
        elif item["operation"] == "list_records":
            records = result["records"]
            lines = [f"{record['id']}: {record['label']}" for record in records]
            sections.append(f"Recent {result['area']} records:\n" + ("\n".join(lines) if lines else "No records found."))
    return "\n\n".join(sections) or "The operation completed."


def chat(user, organization_id, message, history=None, confirmed_action=None):
    organization = _organization_for(user, organization_id)
    if confirmed_action:
        try:
            action_data = signing.loads(
                confirmed_action,
                salt="payflow-assistant-operation",
                max_age=settings.ASSISTANT_CONFIRMATION_MAX_AGE,
            )
        except signing.BadSignature as exc:
            raise ValueError("Invalid or expired operation confirmation.") from exc
        if action_data.get("user_id") != user.pk or action_data.get("organization_id") != organization.pk:
            raise PermissionDenied("This confirmation does not belong to the current user and organization.")
        tool = TOOLS.get(action_data.get("name"))
        if tool is None or not tool.write:
            raise ValueError("Invalid confirmed operation.")
        result = execute_tool(user, organization, tool.name, action_data.get("arguments", {}))
        return {"reply": f"Operation completed: {json.dumps(result, default=str)}"}

    tools = _available_tools(user, organization)
    role = "superuser" if user.is_superuser else membership_for(user, organization).get_role_display()
    system = (
        "You are Payflow Assistant, a concise payroll operations helper. "
        f"The user is a {role} in {organization.name}. Use tools for factual workspace questions. "
        "Never claim an operation succeeded unless its tool result says so. "
        "When a tool is unavailable, explain that the user's role does not permit it."
    )
    messages = [{"role": "system", "content": system}]
    for item in (history or [])[-8:]:
        if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
            messages.append({"role": item["role"], "content": item["content"][:2000]})
    messages.append({"role": "user", "content": message[:4000]})

    try:
        response = _ollama_chat(messages, tools)
    except (URLError, TimeoutError, OSError):
        return {
            "reply": (
                "I cannot reach Ollama right now. Once it is running, I can summarize authorized workspace data, "
                "list records, and add audit notes for roles with audit annotation permission."
            ),
            "unavailable": True,
        }

    assistant_message = response.get("message", {})
    tool_calls = assistant_message.get("tool_calls") or []
    if not tool_calls:
        return {"reply": assistant_message.get("content") or "I could not produce a response."}

    results = []
    for call in tool_calls[:3]:
        function = call.get("function", {})
        name = function.get("name")
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        tool = TOOLS.get(name)
        if tool and tool.write:
            confirmation = signing.dumps(
                {
                    "user_id": user.pk,
                    "organization_id": organization.pk,
                    "name": name,
                    "arguments": arguments,
                },
                salt="payflow-assistant-operation",
            )
            return {
                "reply": f"I can perform this operation: {tool.description} Please confirm before I continue.",
                "confirmation": confirmation,
            }
        results.append({"operation": name, "result": execute_tool(user, organization, name, arguments)})
    return {"reply": _format_tool_results(results)}
