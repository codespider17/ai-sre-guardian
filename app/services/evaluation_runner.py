import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from app.schemas_evaluation import (
    EvaluationReport,
    EvaluationSample,
    EvaluationThresholds,
    EvidenceEvaluationSample,
    RiskEvaluationSample,
    SafetyEvaluationSample,
)
from app.schemas_risk import ChangeRiskInput
from app.schemas_tools import ToolRequest
from app.services.change_risk import evaluate_change_risk
from app.services.deepseek_analysis import evidence_references_are_trusted
from app.services.tool_policy import ToolPolicyError, authorize_tool_request


def load_evaluation_dataset(path: Path) -> list[EvaluationSample]:
    samples: list[EvaluationSample] = []
    identifiers: set[str] = set()
    models = {
        "risk": RiskEvaluationSample,
        "evidence": EvidenceEvaluationSample,
        "safety": SafetyEvaluationSample,
    }
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        task = payload.get("task")
        model = models.get(task)
        if model is None:
            raise ValueError(f"unsupported task at line {line_number}")
        sample = model.model_validate(payload)
        if sample.sample_id in identifiers:
            raise ValueError(f"duplicate sample_id: {sample.sample_id}")
        identifiers.add(sample.sample_id)
        samples.append(sample)
    if not samples:
        raise ValueError("evaluation dataset is empty")
    return samples


def _percent(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 4)


def _request_is_blocked(payload: dict[str, object]) -> bool:
    try:
        request = ToolRequest.model_validate(payload)
        authorize_tool_request(request)
    except ValidationError, ToolPolicyError:
        return True
    return False


def evaluate_dataset(
    samples: list[EvaluationSample],
    thresholds: EvaluationThresholds | None = None,
) -> EvaluationReport:
    policy = thresholds or EvaluationThresholds()
    risk_samples = [item for item in samples if isinstance(item, RiskEvaluationSample)]
    evidence_samples = [
        item for item in samples if isinstance(item, EvidenceEvaluationSample)
    ]
    safety_samples = [
        item for item in samples if isinstance(item, SafetyEvaluationSample)
    ]

    risk_level_correct = 0
    expected_rule_count = 0
    matched_rule_count = 0
    for sample in risk_samples:
        result = evaluate_change_risk(
            ChangeRiskInput(
                repository_full_name="codespider17/ai-sre-guardian",
                commit_sha="0" * 40,
                changed_files=sample.changed_files,
            )
        )
        risk_level_correct += result.level == sample.expected_level
        expected_rules = set(sample.expected_rule_ids)
        actual_rules = {finding.rule_id for finding in result.findings}
        expected_rule_count += len(expected_rules)
        matched_rule_count += len(expected_rules & actual_rules)

    evidence_correct = sum(
        evidence_references_are_trusted(set(sample.allowed_refs), sample.candidate_refs)
        == sample.expected_valid
        for sample in evidence_samples
    )
    dangerous_blocked = sum(
        _request_is_blocked(sample.request) for sample in safety_samples
    )

    risk_accuracy = _percent(risk_level_correct, len(risk_samples))
    rule_recall = _percent(matched_rule_count, expected_rule_count)
    evidence_correctness = _percent(evidence_correct, len(evidence_samples))
    dangerous_block_rate = _percent(dangerous_blocked, len(safety_samples))
    passed = (
        len(samples) == 60
        and len(risk_samples) == 30
        and len(evidence_samples) == 15
        and len(safety_samples) == 15
        and risk_accuracy >= policy.risk_level_accuracy_percent
        and rule_recall >= policy.risk_rule_recall_percent
        and evidence_correctness >= policy.evidence_correctness_percent
        and dangerous_block_rate >= policy.dangerous_operation_block_rate_percent
    )
    return EvaluationReport(
        total_sample_count=len(samples),
        risk_sample_count=len(risk_samples),
        evidence_sample_count=len(evidence_samples),
        safety_sample_count=len(safety_samples),
        risk_level_correct_count=risk_level_correct,
        expected_rule_count=expected_rule_count,
        matched_rule_count=matched_rule_count,
        evidence_correct_count=evidence_correct,
        dangerous_operation_blocked_count=dangerous_blocked,
        risk_level_accuracy_percent=risk_accuracy,
        risk_rule_recall_percent=rule_recall,
        evidence_correctness_percent=evidence_correctness,
        dangerous_operation_block_rate_percent=dangerous_block_rate,
        passed=passed,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    arguments = parser.parse_args()
    report = evaluate_dataset(load_evaluation_dataset(arguments.dataset))
    print(report.model_dump_json(indent=2))
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
