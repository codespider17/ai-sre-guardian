from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentState(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    VALIDATING = "validating"
    RECOMMENDING = "recommending"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStep(BaseModel):
    sequence: int = Field(ge=1)
    from_state: AgentState
    to_state: AgentState
    reason: str = Field(min_length=1, max_length=500)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentRun(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    analysis_run_id: UUID
    state: AgentState = AgentState.CREATED
    planned_tools: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    recommendation: str | None = None
    failure_reason: str | None = None
    steps: list[AgentStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
