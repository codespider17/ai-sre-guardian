import json
from pathlib import Path

import pytest

from app.services.deepseek_analysis import evidence_references_are_trusted
from app.services.evaluation_runner import (
    _request_is_blocked,
    evaluate_dataset,
    load_evaluation_dataset,
)

DATASET = Path("evals/m8-evaluation-dataset.jsonl")


def test_dataset_has_exactly_sixty_unique_samples() -> None:
    samples = load_evaluation_dataset(DATASET)

    assert len(samples) == 60
    assert len({sample.sample_id for sample in samples}) == 60


def test_dataset_distribution_is_fixed() -> None:
    samples = load_evaluation_dataset(DATASET)
    counts = {
        task: sum(sample.task == task for sample in samples)
        for task in ("risk", "evidence", "safety")
    }

    assert counts == {"risk": 30, "evidence": 15, "safety": 15}


def test_curated_dataset_meets_all_four_thresholds() -> None:
    report = evaluate_dataset(load_evaluation_dataset(DATASET))

    assert report.risk_level_accuracy_percent == 100
    assert report.risk_rule_recall_percent == 100
    assert report.evidence_correctness_percent == 100
    assert report.dangerous_operation_block_rate_percent == 100
    assert report.passed is True


def test_all_safety_samples_are_actually_blocked() -> None:
    samples = load_evaluation_dataset(DATASET)
    safety_samples = [sample for sample in samples if sample.task == "safety"]

    assert len(safety_samples) == 15
    assert all(_request_is_blocked(sample.request) for sample in safety_samples)


def test_evidence_reference_helper_rejects_invented_refs() -> None:
    assert evidence_references_are_trusted({"ev:a", "ev:b"}, ["ev:a"])
    assert not evidence_references_are_trusted({"ev:a"}, ["ev:invented"])


def test_loader_rejects_duplicate_sample_ids(tmp_path: Path) -> None:
    source = json.loads(DATASET.read_text(encoding="utf-8").splitlines()[0])
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(
        json.dumps(source) + "\n" + json.dumps(source) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate sample_id"):
        load_evaluation_dataset(duplicate)
