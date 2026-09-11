from enum import StrEnum
from uuid import UUID

from app.schemas_tools import (
    AuthorizedToolCall,
    KubernetesResourceKind,
    ToolName,
    ToolRequest,
    ToolSpec,
)

POLICY_VERSION = "m3-a2-v1"
ALLOWED_NAMESPACES = frozenset({"ai-sre-system", "ai-sre-lab"})

TOOL_REGISTRY: dict[ToolName, ToolSpec] = {
    ToolName.KUBERNETES_WORKLOAD: ToolSpec(
        name=ToolName.KUBERNETES_WORKLOAD,
        capability="read one Kubernetes workload or service",
    ),
    ToolName.KUBERNETES_EVENTS: ToolSpec(
        name=ToolName.KUBERNETES_EVENTS,
        capability="read bounded Kubernetes events",
    ),
    ToolName.KUBERNETES_LOGS: ToolSpec(
        name=ToolName.KUBERNETES_LOGS,
        capability="read bounded pod logs",
    ),
    ToolName.PROMETHEUS_QUERY: ToolSpec(
        name=ToolName.PROMETHEUS_QUERY,
        capability="execute one approved Prometheus query template",
    ),
    ToolName.CHANGE_RISK: ToolSpec(
        name=ToolName.CHANGE_RISK,
        capability="read one persisted change risk result",
    ),
    ToolName.ANALYSIS_EVIDENCE: ToolSpec(
        name=ToolName.ANALYSIS_EVIDENCE,
        capability="read bounded evidence for one analysis run",
    ),
}

FIELD_ALLOWLIST: dict[ToolName, frozenset[str]] = {
    ToolName.KUBERNETES_WORKLOAD: frozenset(
        {"namespace", "resource_kind", "resource_name"}
    ),
    ToolName.KUBERNETES_EVENTS: frozenset(
        {"namespace", "resource_kind", "resource_name", "limit"}
    ),
    ToolName.KUBERNETES_LOGS: frozenset(
        {"namespace", "resource_kind", "resource_name", "limit"}
    ),
    ToolName.PROMETHEUS_QUERY: frozenset({"namespace", "service_name", "query_id"}),
    ToolName.CHANGE_RISK: frozenset({"analysis_run_id"}),
    ToolName.ANALYSIS_EVIDENCE: frozenset({"analysis_run_id", "limit"}),
}

REQUIRED_FIELDS: dict[ToolName, frozenset[str]] = {
    ToolName.KUBERNETES_WORKLOAD: frozenset(
        {"namespace", "resource_kind", "resource_name"}
    ),
    ToolName.KUBERNETES_EVENTS: frozenset(
        {"namespace", "resource_kind", "resource_name"}
    ),
    ToolName.KUBERNETES_LOGS: frozenset(
        {"namespace", "resource_kind", "resource_name"}
    ),
    ToolName.PROMETHEUS_QUERY: frozenset({"namespace", "service_name", "query_id"}),
    ToolName.CHANGE_RISK: frozenset({"analysis_run_id"}),
    ToolName.ANALYSIS_EVIDENCE: frozenset({"analysis_run_id"}),
}


class ToolPolicyError(ValueError):
    pass


class ToolInputError(ToolPolicyError):
    pass


class ToolAccessDeniedError(ToolPolicyError):
    pass


def _provided_fields(request: ToolRequest) -> set[str]:
    names = {
        "namespace",
        "resource_kind",
        "resource_name",
        "service_name",
        "query_id",
        "analysis_run_id",
    }
    provided = {name for name in names if getattr(request, name) is not None}
    if "limit" in request.model_fields_set:
        provided.add("limit")
    return provided


def _serialize(value: object) -> str | int:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, int | str):
        return value
    raise ToolInputError("unsupported tool argument type")


def authorize_tool_request(request: ToolRequest) -> AuthorizedToolCall:
    allowed_fields = FIELD_ALLOWLIST[request.tool]
    unexpected = _provided_fields(request) - allowed_fields
    if unexpected:
        raise ToolInputError(
            "fields are not allowed for tool: " + ",".join(sorted(unexpected))
        )

    missing = {
        name for name in REQUIRED_FIELDS[request.tool] if getattr(request, name) is None
    }
    if missing:
        raise ToolInputError(
            "required fields are missing: " + ",".join(sorted(missing))
        )

    if request.namespace is not None and request.namespace not in ALLOWED_NAMESPACES:
        raise ToolAccessDeniedError("namespace is outside the allowlist")

    if (
        request.tool == ToolName.KUBERNETES_LOGS
        and request.resource_kind != KubernetesResourceKind.POD
    ):
        raise ToolAccessDeniedError("logs are allowed only for pods")

    if request.tool == ToolName.KUBERNETES_EVENTS and request.limit > 100:
        raise ToolAccessDeniedError("event result limit cannot exceed 100")

    arguments: dict[str, str | int] = {}
    for field_name in sorted(allowed_fields):
        value = getattr(request, field_name)
        if value is not None:
            arguments[field_name] = _serialize(value)

    return AuthorizedToolCall(
        tool=request.tool,
        policy_version=POLICY_VERSION,
        arguments=arguments,
    )
