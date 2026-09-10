from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "critical"]


class ChangeRiskInput(BaseModel):
    repository_full_name: str = Field(min_length=3, max_length=200)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    changed_files: list[str] = Field(min_length=1, max_length=500)


class RiskFinding(BaseModel):
    rule_id: str
    score: int = Field(ge=0, le=100)
    title: str
    explanation: str
    evidence_files: list[str]


class ChangeRiskResult(BaseModel):
    score: int = Field(ge=0, le=100)
    level: RiskLevel
    findings: list[RiskFinding]
    evaluated_file_count: int = Field(ge=1)
