from pydantic import BaseModel, ConfigDict, Field, model_validator


class CapacityBaselinePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_requests_per_second: float = Field(gt=0)
    maximum_p95_latency_ms: float = Field(gt=0)
    maximum_error_rate_percent: float = Field(ge=0, le=100)
    maximum_cpu_millicores: float = Field(gt=0)
    maximum_memory_mib: float = Field(gt=0)


class CapacityBaselineSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    virtual_users: int = Field(ge=1, le=10_000)
    duration_seconds: float = Field(gt=0)
    total_requests: int = Field(ge=1)
    failed_requests: int = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    peak_cpu_millicores: float = Field(gt=0)
    peak_memory_mib: float = Field(gt=0)
    initial_replicas: int = Field(ge=1)
    peak_replicas: int = Field(ge=1)
    evidence_refs: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_counts_and_replicas(self) -> CapacityBaselineSample:
        if self.failed_requests > self.total_requests:
            raise ValueError("failed requests cannot exceed total requests")
        if self.peak_replicas < self.initial_replicas:
            raise ValueError("peak replicas cannot be below initial replicas")
        return self


class CapacityBaselineResult(BaseModel):
    virtual_users: int
    duration_seconds: float
    total_requests: int
    successful_requests: int
    requests_per_second: float
    successful_requests_per_second: float
    error_rate_percent: float
    p95_latency_ms: float
    peak_cpu_millicores: float
    peak_memory_mib: float
    requests_per_cpu_core: float
    requests_per_memory_gib: float
    scale_out_ratio: float
    passed: bool
    limit_reason_codes: list[str]
    evidence_refs: list[str]
