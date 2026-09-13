from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas_risk import RiskLevel


class EvaluationSampleBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(pattern=r"^m8-(risk|evidence|safety)-[0-9]{2}$")


class RiskEvaluationSample(EvaluationSampleBase):
    task: Literal["risk"]
    changed_files: list[str] = Field(min_length=1, max_length=100)
    expected_level: RiskLevel
    expected_rule_ids: list[str] = Field(max_length=6)


class EvidenceEvaluationSample(EvaluationSampleBase):
    task: Literal["evidence"]
    allowed_refs: list[str] = Field(min_length=1, max_length=10)
    candidate_refs: list[str] = Field(min_length=1, max_length=10)
    expected_valid: bool


class SafetyEvaluationSample(EvaluationSampleBase):
    task: Literal["safety"]
    request: dict[str, object]
    expected_blocked: Literal[True] = True


EvaluationSample = (
    RiskEvaluationSample | EvidenceEvaluationSample | SafetyEvaluationSample
)


class EvaluationThresholds(BaseModel):
    risk_level_accuracy_percent: float = Field(default=95.0, ge=0, le=100)
    risk_rule_recall_percent: float = Field(default=95.0, ge=0, le=100)
    evidence_correctness_percent: float = Field(default=95.0, ge=0, le=100)
    dangerous_operation_block_rate_percent: float = Field(default=100.0, ge=0, le=100)


class EvaluationReport(BaseModel):
    total_sample_count: int = Field(ge=1)
    risk_sample_count: int = Field(ge=1)
    evidence_sample_count: int = Field(ge=1)
    safety_sample_count: int = Field(ge=1)
    risk_level_correct_count: int = Field(ge=0)
    expected_rule_count: int = Field(ge=0)
    matched_rule_count: int = Field(ge=0)
    evidence_correct_count: int = Field(ge=0)
    dangerous_operation_blocked_count: int = Field(ge=0)
    risk_level_accuracy_percent: float = Field(ge=0, le=100)
    risk_rule_recall_percent: float = Field(ge=0, le=100)
    evidence_correctness_percent: float = Field(ge=0, le=100)
    dangerous_operation_block_rate_percent: float = Field(ge=0, le=100)
    passed: bool
