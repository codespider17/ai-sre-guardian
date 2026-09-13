from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RateLimitExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$",
    )


class RateLimitExperimentReceipt(BaseModel):
    strategy: Literal["rate_limit"] = "rate_limit"
    outcome: Literal["allowed"] = "allowed"
    limit: int
    remaining: int
    window_seconds: int
    automated_mutation_allowed: bool = False


class DegradationExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dependency_available: bool


class DegradationExperimentReceipt(BaseModel):
    strategy: Literal["graceful_degradation"] = "graceful_degradation"
    outcome: Literal["normal", "degraded"]
    response_source: Literal["dependency", "fallback"]
    automated_mutation_allowed: bool = False
