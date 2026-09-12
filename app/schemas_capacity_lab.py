from pydantic import BaseModel, ConfigDict, Field


class CapacityWorkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iterations: int = Field(ge=100, le=250_000)
    seed: int = Field(ge=0, le=1_000_000)


class CapacityWorkReceipt(BaseModel):
    iterations: int
    seed: int
    checksum: int
    duration_ms: float
