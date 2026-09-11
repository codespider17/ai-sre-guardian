import json
import subprocess
from collections.abc import Callable
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisRun, EvidenceItem
from app.schemas_tool_execution import ToolExecutionResult
from app.schemas_tools import (
    AuthorizedToolCall,
    PrometheusQueryId,
    ToolName,
    ToolRequest,
)
from app.services.tool_policy import authorize_tool_request

COMMAND_SHELL_ENABLED = False
COMMAND_TIMEOUT_SECONDS = 15
MAX_TEXT_CHARACTERS = 65_536
DEFAULT_PROMETHEUS_URL = "http://127.0.0.1:19090"

CommandRunner = Callable[[list[str]], str]
PrometheusReader = Callable[[str], dict[str, Any]]


class ToolExecutionError(RuntimeError):
    pass


def run_read_only_command(arguments: list[str]) -> str:
    completed = subprocess.run(
        arguments,
        check=True,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        shell=COMMAND_SHELL_ENABLED,
    )
    return completed.stdout


def read_prometheus_query(query: str) -> dict[str, Any]:
    response = httpx.get(
        f"{DEFAULT_PROMETHEUS_URL}/api/v1/query",
        params={"query": query},
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "success":
        raise ToolExecutionError("Prometheus query did not succeed")
    return payload


def build_prometheus_query(
    query_id: PrometheusQueryId,
    namespace: str,
    service_name: str,
) -> str:
    selector = f'namespace="{namespace}",service="{service_name}"'
    queries = {
        PrometheusQueryId.WORKLOAD_AVAILABILITY: (
            "avg(kube_deployment_status_replicas_available"
            f'{{namespace="{namespace}",deployment="{service_name}"}})'
        ),
        PrometheusQueryId.HTTP_ERROR_RATIO: (
            f'sum(rate(http_requests_total{{{selector},status=~"5.."}}[5m])) '
            f"/ clamp_min(sum(rate(http_requests_total{{{selector}}}[5m])), 1)"
        ),
        PrometheusQueryId.HTTP_P95_LATENCY: (
            "histogram_quantile(0.95, sum by (le) "
            f"(rate(http_request_duration_seconds_bucket{{{selector}}}[5m])))"
        ),
        PrometheusQueryId.CPU_UTILIZATION: (
            "sum(rate(container_cpu_usage_seconds_total"
            f'{{namespace="{namespace}",pod=~"{service_name}-.+"}}[5m]))'
        ),
    }
    return queries[query_id]


def _bounded_text(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_CHARACTERS:
        return text, False
    return text[:MAX_TEXT_CHARACTERS], True


def _run_kubernetes_tool(
    call: AuthorizedToolCall,
    command_runner: CommandRunner,
) -> tuple[dict[str, Any], bool]:
    namespace = str(call.arguments["namespace"])
    resource_kind = str(call.arguments["resource_kind"])
    resource_name = str(call.arguments["resource_name"])

    if call.tool == ToolName.KUBERNETES_WORKLOAD:
        output = command_runner(
            [
                "kubectl",
                "-n",
                namespace,
                "get",
                resource_kind,
                resource_name,
                "-o",
                "json",
            ]
        )
        return {"object": json.loads(output)}, False

    if call.tool == ToolName.KUBERNETES_EVENTS:
        limit = int(call.arguments.get("limit", 50))
        output = command_runner(
            [
                "kubectl",
                "-n",
                namespace,
                "get",
                "events",
                "--field-selector",
                (
                    f"involvedObject.kind={resource_kind},"
                    f"involvedObject.name={resource_name}"
                ),
                "--sort-by=.lastTimestamp",
                "-o",
                "json",
            ]
        )
        document = json.loads(output)
        items = document.get("items", [])
        return {"items": items[-limit:]}, len(items) > limit

    if call.tool == ToolName.KUBERNETES_LOGS:
        limit = int(call.arguments.get("limit", 50))
        output = command_runner(
            [
                "kubectl",
                "-n",
                namespace,
                "logs",
                f"pod/{resource_name}",
                f"--tail={limit}",
            ]
        )
        bounded, truncated = _bounded_text(output)
        return {"text": bounded, "line_limit": limit}, truncated

    raise ToolExecutionError("unsupported Kubernetes tool")


def _read_change_risk(
    session: Session,
    analysis_run_id: UUID,
) -> dict[str, Any]:
    analysis = session.get(AnalysisRun, analysis_run_id)
    if analysis is None:
        raise ToolExecutionError("analysis run was not found")
    return {
        "analysis_run_id": str(analysis.id),
        "status": analysis.status,
        "risk_score": analysis.risk_score,
        "risk_level": analysis.risk_level,
        "summary": analysis.summary,
    }


def _read_analysis_evidence(
    session: Session,
    analysis_run_id: UUID,
    limit: int,
) -> tuple[dict[str, Any], bool]:
    analysis = session.get(AnalysisRun, analysis_run_id)
    if analysis is None:
        raise ToolExecutionError("analysis run was not found")
    all_items = session.scalars(
        select(EvidenceItem)
        .where(EvidenceItem.analysis_run_id == analysis_run_id)
        .order_by(EvidenceItem.observed_at, EvidenceItem.id)
    ).all()
    selected = all_items[:limit]
    return {
        "analysis_run_id": str(analysis_run_id),
        "items": [
            {
                "evidence_key": item.evidence_key,
                "source_type": item.source_type,
                "source_ref": item.source_ref,
                "payload": item.payload,
            }
            for item in selected
        ],
    }, len(all_items) > limit


def execute_read_only_tool(
    session: Session,
    request: ToolRequest,
    command_runner: CommandRunner = run_read_only_command,
    prometheus_reader: PrometheusReader = read_prometheus_query,
) -> ToolExecutionResult:
    call = authorize_tool_request(request)
    started = perf_counter()
    truncated = False

    try:
        if call.tool in {
            ToolName.KUBERNETES_WORKLOAD,
            ToolName.KUBERNETES_EVENTS,
            ToolName.KUBERNETES_LOGS,
        }:
            payload, truncated = _run_kubernetes_tool(call, command_runner)
        elif call.tool == ToolName.PROMETHEUS_QUERY:
            query = build_prometheus_query(
                PrometheusQueryId(str(call.arguments["query_id"])),
                str(call.arguments["namespace"]),
                str(call.arguments["service_name"]),
            )
            payload = prometheus_reader(query)
        elif call.tool == ToolName.CHANGE_RISK:
            payload = _read_change_risk(
                session,
                UUID(str(call.arguments["analysis_run_id"])),
            )
        elif call.tool == ToolName.ANALYSIS_EVIDENCE:
            payload, truncated = _read_analysis_evidence(
                session,
                UUID(str(call.arguments["analysis_run_id"])),
                int(call.arguments.get("limit", 50)),
            )
        else:
            raise ToolExecutionError("tool is not implemented")
    except ToolExecutionError:
        raise
    except Exception as exc:
        raise ToolExecutionError(f"{call.tool} execution failed") from exc

    duration_ms = max(0, int((perf_counter() - started) * 1000))
    return ToolExecutionResult(
        tool=call.tool,
        payload=payload,
        truncated=truncated,
        duration_ms=duration_ms,
    )
