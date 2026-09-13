from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResilienceStrategy(StrEnum):
    RATE_LIMIT = "rate_limit"
    GRACEFUL_DEGRADATION = "graceful_degradation"
    FAULT_TOLERANCE = "fault_tolerance"
    AUTOSCALING = "autoscaling"
    ROLLBACK = "rollback"


class ResilienceExperimentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_expected_outcome_percent: float = Field(ge=0, le=100)
    minimum_control_event_count: int = Field(ge=1)
    maximum_recovery_time_seconds: float = Field(gt=0)
    maximum_unexpected_error_count: int = Field(ge=0)
    maximum_data_loss_count: int = Field(ge=0)


class ResilienceExperimentSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: ResilienceStrategy
    total_request_count: int = Field(ge=1)
    expected_outcome_count: int = Field(ge=0)
    unexpected_error_count: int = Field(ge=0)
    control_event_count: int = Field(ge=0)
    recovery_time_seconds: float = Field(ge=0)
    service_recovered: bool
    state_restored: bool
    data_loss_count: int = Field(ge=0)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_counts_and_evidence(self) -> ResilienceExperimentSample:
        classified_count = self.expected_outcome_count + self.unexpected_error_count
        if classified_count > self.total_request_count:
            raise ValueError("classified outcomes cannot exceed total requests")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence references must be unique")
        return self


class ResilienceExperimentResult(BaseModel):
    strategy: ResilienceStrategy
    control_metric_name: str
    total_request_count: int
    expected_outcome_count: int
    expected_outcome_percent: float
    unexpected_error_count: int
    control_event_count: int
    recovery_time_seconds: float
    service_recovered: bool
    state_restored: bool
    data_loss_count: int
    passed: bool
    reason_codes: list[str]
    evidence_refs: list[str]
    automated_mutation_allowed: bool = False
