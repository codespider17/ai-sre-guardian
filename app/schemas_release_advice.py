from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas_devflow import DevFlowReleaseStatus

RiskLevel = Literal["low", "medium", "high", "critical"]
ReleaseDecision = Literal["proceed", "manual_review", "block"]


class ReleaseAdviceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_status: DevFlowReleaseStatus
    risk_level: RiskLevel | None = None
    error_budget_burn_rate: float | None = Field(default=None, ge=0)
    slo_breached: bool | None = None
    evidence_refs: list[str] = Field(
        default_factory=list,
        max_length=20,
    )


class ReleaseAdviceResult(BaseModel):
    decision: ReleaseDecision
    human_approval_required: bool
    automated_mutation_allowed: bool
    reason_codes: list[str]
    evidence_refs: list[str]
