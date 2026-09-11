from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SLIType(StrEnum):
    AVAILABILITY = "availability"
    ERROR_RATE = "error_rate"
    LATENCY_COMPLIANCE = "latency_compliance"
    SATURATION_COMPLIANCE = "saturation_compliance"


class ReliabilitySample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_requests: int = Field(gt=0)
    successful_requests: int = Field(ge=0)
    latency_good_requests: int = Field(ge=0)
    saturation_sample_count: int = Field(gt=0)
    saturation_good_samples: int = Field(ge=0)
    downtime_minutes: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_counters(self) -> Self:
        if self.successful_requests > self.total_requests:
            raise ValueError("successful_requests cannot exceed total_requests")
        if self.latency_good_requests > self.total_requests:
            raise ValueError("latency_good_requests cannot exceed total_requests")
        if self.saturation_good_samples > self.saturation_sample_count:
            raise ValueError("saturation_good_samples cannot exceed sample count")
        return self


class SLIResult(BaseModel):
    sli_type: SLIType
    value_percent: float = Field(ge=0, le=100)
    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)


class SLODefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    sli_type: SLIType
    objective_percent: float = Field(gt=0, lt=100)
    window_minutes: int = Field(gt=0)


class SLOEvaluation(BaseModel):
    name: str
    sli_type: SLIType
    objective_percent: float
    achieved_percent: float
    observed_bad_event_count: int
    allowed_bad_event_count: float
    error_budget_percent: float
    remaining_error_budget_percent: float
    error_budget_consumption_percent: float
    burn_rate: float
    breached: bool
    allowed_downtime_minutes: float | None = None
    observed_downtime_minutes: float | None = None
    sla_impact_minutes: float | None = None
