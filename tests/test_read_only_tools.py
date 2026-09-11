import json
from uuid import uuid4

import pytest

from app.database import SessionLocal
from app.schemas_tools import (
    KubernetesResourceKind,
    PrometheusQueryId,
    ToolName,
    ToolRequest,
)
from app.services.read_only_tools import (
    COMMAND_SHELL_ENABLED,
    MAX_TEXT_CHARACTERS,
    ToolExecutionError,
    build_prometheus_query,
    execute_read_only_tool,
)
from app.services.tool_policy import ToolAccessDeniedError


def test_workload_executor_builds_fixed_argument_vector() -> None:
    captured: list[list[str]] = []

    def runner(arguments: list[str]) -> str:
        captured.append(arguments)
        return json.dumps({"kind": "Deployment", "metadata": {"name": "api"}})

    with SessionLocal() as session:
        result = execute_read_only_tool(
            session,
            ToolRequest(
                tool=ToolName.KUBERNETES_WORKLOAD,
                namespace="ai-sre-system",
                resource_kind=KubernetesResourceKind.DEPLOYMENT,
                resource_name="api",
            ),
            command_runner=runner,
        )
    assert captured == [
        [
            "kubectl",
            "-n",
            "ai-sre-system",
            "get",
            "deployment",
            "api",
            "-o",
            "json",
        ]
    ]
    assert result.payload["object"]["kind"] == "Deployment"


def test_event_executor_applies_result_limit() -> None:
    def runner(arguments: list[str]) -> str:
        assert "--field-selector" in arguments
        return json.dumps({"items": [{"id": index} for index in range(5)]})

    with SessionLocal() as session:
        result = execute_read_only_tool(
            session,
            ToolRequest(
                tool=ToolName.KUBERNETES_EVENTS,
                namespace="ai-sre-lab",
                resource_kind=KubernetesResourceKind.POD,
                resource_name="fault-target",
                limit=2,
            ),
            command_runner=runner,
        )
    assert [item["id"] for item in result.payload["items"]] == [3, 4]
    assert result.truncated is True


def test_log_executor_uses_tail_and_truncates_large_text() -> None:
    captured: list[list[str]] = []

    def runner(arguments: list[str]) -> str:
        captured.append(arguments)
        return "x" * (MAX_TEXT_CHARACTERS + 10)

    with SessionLocal() as session:
        result = execute_read_only_tool(
            session,
            ToolRequest(
                tool=ToolName.KUBERNETES_LOGS,
                namespace="ai-sre-lab",
                resource_kind=KubernetesResourceKind.POD,
                resource_name="fault-target",
                limit=200,
            ),
            command_runner=runner,
        )
    assert captured[0][-1] == "--tail=200"
    assert len(result.payload["text"]) == MAX_TEXT_CHARACTERS
    assert result.truncated is True


def test_prometheus_executor_uses_approved_template() -> None:
    captured: list[str] = []

    def reader(query: str) -> dict[str, object]:
        captured.append(query)
        return {"status": "success", "data": {"result": []}}

    with SessionLocal() as session:
        result = execute_read_only_tool(
            session,
            ToolRequest(
                tool=ToolName.PROMETHEUS_QUERY,
                namespace="ai-sre-system",
                service_name="ai-sre-guardian",
                query_id=PrometheusQueryId.HTTP_ERROR_RATIO,
            ),
            prometheus_reader=reader,
        )
    assert 'namespace="ai-sre-system"' in captured[0]
    assert 'service="ai-sre-guardian"' in captured[0]
    assert result.payload["status"] == "success"


def test_all_prometheus_query_ids_build_nonempty_queries() -> None:
    for query_id in PrometheusQueryId:
        query = build_prometheus_query(
            query_id,
            "ai-sre-system",
            "ai-sre-guardian",
        )
        assert query
        assert "ai-sre-system" in query


def test_change_risk_reads_existing_analysis() -> None:
    analysis_id = "56f3e3d0-b983-4881-b7ba-a46b48099774"
    with SessionLocal() as session:
        result = execute_read_only_tool(
            session,
            ToolRequest(
                tool=ToolName.CHANGE_RISK,
                analysis_run_id=analysis_id,
            ),
        )
    assert result.payload["risk_score"] == 100
    assert result.payload["risk_level"] == "critical"


def test_evidence_reader_returns_bounded_items() -> None:
    analysis_id = "56f3e3d0-b983-4881-b7ba-a46b48099774"
    with SessionLocal() as session:
        result = execute_read_only_tool(
            session,
            ToolRequest(
                tool=ToolName.ANALYSIS_EVIDENCE,
                analysis_run_id=analysis_id,
                limit=2,
            ),
        )
    assert len(result.payload["items"]) == 2
    assert result.truncated is True


def test_missing_analysis_returns_sanitized_error() -> None:
    with (
        SessionLocal() as session,
        pytest.raises(ToolExecutionError, match="was not found"),
    ):
        execute_read_only_tool(
            session,
            ToolRequest(
                tool=ToolName.CHANGE_RISK,
                analysis_run_id=uuid4(),
            ),
        )


def test_policy_denial_happens_before_command_runner() -> None:
    called = False

    def runner(arguments: list[str]) -> str:
        nonlocal called
        called = True
        return "{}"

    with SessionLocal() as session, pytest.raises(ToolAccessDeniedError):
        execute_read_only_tool(
            session,
            ToolRequest(
                tool=ToolName.KUBERNETES_WORKLOAD,
                namespace="kube-system",
                resource_kind=KubernetesResourceKind.DEPLOYMENT,
                resource_name="coredns",
            ),
            command_runner=runner,
        )
    assert called is False


def test_command_execution_never_enables_shell() -> None:
    assert COMMAND_SHELL_ENABLED is False
