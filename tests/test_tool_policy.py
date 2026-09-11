from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas_tools import (
    KubernetesResourceKind,
    PrometheusQueryId,
    ToolName,
    ToolRequest,
)
from app.services.tool_policy import (
    ALLOWED_NAMESPACES,
    TOOL_REGISTRY,
    ToolAccessDeniedError,
    ToolInputError,
    authorize_tool_request,
)


def test_registry_contains_exactly_six_read_only_tools() -> None:
    assert len(TOOL_REGISTRY) == 6
    assert set(TOOL_REGISTRY) == set(ToolName)
    assert all(spec.read_only for spec in TOOL_REGISTRY.values())


def test_kubernetes_workload_request_is_authorized() -> None:
    call = authorize_tool_request(
        ToolRequest(
            tool=ToolName.KUBERNETES_WORKLOAD,
            namespace="ai-sre-system",
            resource_kind=KubernetesResourceKind.DEPLOYMENT,
            resource_name="ai-sre-guardian",
        )
    )
    assert call.read_only is True
    assert call.arguments["namespace"] == "ai-sre-system"


def test_namespace_outside_allowlist_is_denied() -> None:
    with pytest.raises(ToolAccessDeniedError, match="allowlist"):
        authorize_tool_request(
            ToolRequest(
                tool=ToolName.KUBERNETES_WORKLOAD,
                namespace="kube-system",
                resource_kind=KubernetesResourceKind.DEPLOYMENT,
                resource_name="coredns",
            )
        )


def test_kubernetes_logs_are_restricted_to_pods() -> None:
    with pytest.raises(ToolAccessDeniedError, match="only for pods"):
        authorize_tool_request(
            ToolRequest(
                tool=ToolName.KUBERNETES_LOGS,
                namespace="ai-sre-lab",
                resource_kind=KubernetesResourceKind.DEPLOYMENT,
                resource_name="fault-target",
            )
        )


def test_kubernetes_resource_name_is_required() -> None:
    with pytest.raises(ToolInputError, match="resource_name"):
        authorize_tool_request(
            ToolRequest(
                tool=ToolName.KUBERNETES_EVENTS,
                namespace="ai-sre-system",
                resource_kind=KubernetesResourceKind.POD,
            )
        )


def test_unknown_tool_name_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        ToolRequest.model_validate({"tool": "delete_pod"})


def test_unknown_prometheus_query_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        ToolRequest.model_validate(
            {
                "tool": "prometheus_query",
                "namespace": "ai-sre-system",
                "service_name": "ai-sre-guardian",
                "query_id": "arbitrary_promql",
            }
        )


def test_approved_prometheus_template_is_authorized() -> None:
    call = authorize_tool_request(
        ToolRequest(
            tool=ToolName.PROMETHEUS_QUERY,
            namespace="ai-sre-system",
            service_name="ai-sre-guardian",
            query_id=PrometheusQueryId.HTTP_ERROR_RATIO,
        )
    )
    assert call.arguments["query_id"] == "http_error_ratio"


def test_database_read_tools_require_analysis_id() -> None:
    analysis_id = uuid4()
    for tool in (ToolName.CHANGE_RISK, ToolName.ANALYSIS_EVIDENCE):
        call = authorize_tool_request(
            ToolRequest(tool=tool, analysis_run_id=analysis_id)
        )
        assert call.arguments["analysis_run_id"] == str(analysis_id)


def test_database_read_tool_rejects_missing_analysis_id() -> None:
    with pytest.raises(ToolInputError, match="analysis_run_id"):
        authorize_tool_request(ToolRequest(tool=ToolName.CHANGE_RISK))


def test_extra_command_field_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        ToolRequest.model_validate({"tool": "change_risk", "command": "rm -rf /"})


def test_irrelevant_field_is_rejected_by_policy() -> None:
    with pytest.raises(ToolInputError, match="not allowed"):
        authorize_tool_request(
            ToolRequest(
                tool=ToolName.CHANGE_RISK,
                analysis_run_id=uuid4(),
                namespace="ai-sre-system",
            )
        )


def test_event_limit_is_bounded_to_one_hundred() -> None:
    base = {
        "tool": ToolName.KUBERNETES_EVENTS,
        "namespace": "ai-sre-lab",
        "resource_kind": KubernetesResourceKind.POD,
        "resource_name": "fault-target",
    }
    assert authorize_tool_request(ToolRequest(**base, limit=100)).read_only
    with pytest.raises(ToolAccessDeniedError, match="cannot exceed 100"):
        authorize_tool_request(ToolRequest(**base, limit=101))


def test_log_limit_is_bounded_to_two_hundred() -> None:
    call = authorize_tool_request(
        ToolRequest(
            tool=ToolName.KUBERNETES_LOGS,
            namespace="ai-sre-lab",
            resource_kind=KubernetesResourceKind.POD,
            resource_name="fault-target",
            limit=200,
        )
    )
    assert call.arguments["limit"] == 200
    with pytest.raises(ValidationError):
        ToolRequest(
            tool=ToolName.KUBERNETES_LOGS,
            namespace="ai-sre-lab",
            resource_kind=KubernetesResourceKind.POD,
            resource_name="fault-target",
            limit=201,
        )


def test_namespace_allowlist_contains_only_project_namespaces() -> None:
    assert {"ai-sre-system", "ai-sre-lab"} == ALLOWED_NAMESPACES
