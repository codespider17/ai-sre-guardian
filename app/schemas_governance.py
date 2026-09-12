from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas_release_advice import ReleaseAdviceInput, ReleaseDecision


class ReleaseRecommendationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: UUID
    signals: ReleaseAdviceInput


class ReleaseRecommendationReceipt(BaseModel):
    status: Literal["recorded", "duplicate"]
    recommendation_id: UUID
    observation_id: UUID
    decision: ReleaseDecision
    human_approval_required: bool
    automated_mutation_allowed: bool
    reason_codes: list[str]
    evidence_refs: list[str]
    created_at: datetime


class HumanApprovalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


class HumanApprovalReceipt(BaseModel):
    status: Literal["recorded", "duplicate"]
    approval_id: UUID
    recommendation_id: UUID
    decision: Literal["approved", "rejected"]
    actor: str
    reason: str
    decided_at: datetime
