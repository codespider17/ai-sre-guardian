from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas_risk import RiskLevel


class ChangeEvaluationRequest(BaseModel):
    delivery_id: str = Field(min_length=1, max_length=100)
    repository_full_name: str = Field(min_length=3, max_length=200)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    git_ref: str = Field(min_length=1, max_length=500)
    author: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    changed_files: list[str] = Field(min_length=1, max_length=500)


class ChangeEvaluationReceipt(BaseModel):
    delivery_id: str
    status: Literal["evaluated", "duplicate"]
    change_event_id: UUID
    analysis_run_id: UUID
    risk_score: int
    risk_level: RiskLevel
    finding_count: int
