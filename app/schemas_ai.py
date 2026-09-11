from typing import Literal

from pydantic import BaseModel, Field

from app.schemas_risk import RiskLevel

AIRecommendation = Literal["proceed", "manual_review_required", "block"]
AnalysisMode = Literal["deepseek", "rules_fallback"]


class AnalysisEvidence(BaseModel):
    evidence_ref: str = Field(min_length=1, max_length=200)
    source_type: str = Field(min_length=1, max_length=50)
    content: str = Field(min_length=1, max_length=4000)


class DeepSeekAnalysisInput(BaseModel):
    change_summary: str = Field(min_length=1, max_length=2000)
    deterministic_risk_score: int = Field(ge=0, le=100)
    deterministic_risk_level: RiskLevel
    evidence: list[AnalysisEvidence] = Field(min_length=1, max_length=10)


class StructuredAIAnalysis(BaseModel):
    risk_level: RiskLevel
    summary: str = Field(min_length=1, max_length=1000)
    recommendation: AIRecommendation
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(min_length=1, max_length=10)
    reasoning_points: list[str] = Field(min_length=1, max_length=6)


class AIAnalysisOutcome(BaseModel):
    mode: AnalysisMode
    model: str | None
    analysis: StructuredAIAnalysis
    fallback_reason: str | None = None
