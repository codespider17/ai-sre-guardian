from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ToolName(StrEnum):
    KUBERNETES_WORKLOAD = "kubernetes_workload"
    KUBERNETES_EVENTS = "kubernetes_events"
    KUBERNETES_LOGS = "kubernetes_logs"
    PROMETHEUS_QUERY = "prometheus_query"
    CHANGE_RISK = "change_risk"
    ANALYSIS_EVIDENCE = "analysis_evidence"


class KubernetesResourceKind(StrEnum):
    DEPLOYMENT = "deployment"
    STATEFULSET = "statefulset"
    POD = "pod"
    SERVICE = "service"


class PrometheusQueryId(StrEnum):
    WORKLOAD_AVAILABILITY = "workload_availability"
    HTTP_ERROR_RATIO = "http_error_ratio"
    HTTP_P95_LATENCY = "http_p95_latency"
    CPU_UTILIZATION = "cpu_utilization"


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: ToolName
    namespace: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
        max_length=63,
    )
    resource_kind: KubernetesResourceKind | None = None
    resource_name: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$",
        max_length=253,
    )
    service_name: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
        max_length=63,
    )
    query_id: PrometheusQueryId | None = None
    analysis_run_id: UUID | None = None
    limit: int = Field(default=50, ge=1, le=200)


class ToolSpec(BaseModel):
    name: ToolName
    capability: str
    read_only: Literal[True] = True


class AuthorizedToolCall(BaseModel):
    tool: ToolName
    policy_version: str
    read_only: Literal[True] = True
    arguments: dict[str, str | int]
