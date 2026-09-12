from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DevFlowReleaseStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class DevFlowReleaseObservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: str = Field(min_length=1, max_length=120)
    service_id: UUID
    pipeline_run_id: UUID
    deployment_id: UUID | None = None
    environment: str = Field(min_length=1, max_length=100)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    image_reference: str = Field(min_length=1, max_length=500)
    status: DevFlowReleaseStatus
    observed_at: datetime


class DevFlowReleaseObservationReceipt(BaseModel):
    status: Literal["recorded", "duplicate"]
    observation_id: UUID
    delivery_id: str
    service_id: UUID
    pipeline_run_id: UUID
    deployment_id: UUID | None
    release_status: DevFlowReleaseStatus
    observed_at: datetime
