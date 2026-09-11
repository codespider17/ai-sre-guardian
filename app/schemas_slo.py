from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas_reliability import ReliabilitySample, SLIType


class SLOPolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID
    name: str = Field(min_length=1, max_length=120)
    sli_type: SLIType
    objective_percent: float = Field(gt=0, lt=100)
    window_minutes: int = Field(gt=0)


class SLOPolicyReceipt(BaseModel):
    status: Literal["created", "duplicate"]
    policy_id: UUID
    service_id: UUID
    name: str
    sli_type: SLIType
    objective_percent: float
    window_minutes: int
    active: bool


class SLOEvaluationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_key: str = Field(min_length=1, max_length=100)
    sample: ReliabilitySample


class SLOEvaluationReceipt(BaseModel):
    status: Literal["evaluated", "duplicate"]
    evaluation_id: UUID
    policy_id: UUID
    sample_key: str
    achieved_percent: float
    observed_bad_event_count: int
    allowed_bad_event_count: float
    error_budget_percent: float
    remaining_error_budget_percent: float
    error_budget_consumption_percent: float
    burn_rate: float
    breached: bool
    allowed_downtime_minutes: float | None
    observed_downtime_minutes: float | None
    sla_impact_minutes: float | None
