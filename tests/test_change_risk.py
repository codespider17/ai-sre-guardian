import pytest

from app.schemas_risk import ChangeRiskInput
from app.services.change_risk import RULE_COUNT, evaluate_change_risk


def evaluate(files: list[str]):
    return evaluate_change_risk(
        ChangeRiskInput(
            repository_full_name="codespider17/ai-sre-guardian",
            commit_sha="a" * 40,
            changed_files=files,
        )
    )


def test_exactly_six_rules_are_registered() -> None:
    assert RULE_COUNT == 6


def test_document_change_is_low_risk() -> None:
    result = evaluate(["README.md"])
    assert result.score == 0
    assert result.level == "low"
    assert result.findings == []


@pytest.mark.parametrize(
    ("files", "rule_id"),
    [
        (["alembic/versions/next.py"], "database_migration"),
        (
            ["deploy/helm/ai-sre/templates/deployment.yaml"],
            "kubernetes_infrastructure",
        ),
        (["ci/Jenkinsfile"], "ci_cd_pipeline"),
        (["requirements.lock"], "dependency_or_image"),
        (["deploy/kubernetes/rbac.yaml"], "security_boundary"),
        (
            [f"app/module_{index}.py" for index in range(20)],
            "large_change",
        ),
    ],
)
def test_each_rule_returns_evidence(
    files: list[str],
    rule_id: str,
) -> None:
    result = evaluate(files)
    finding = next(item for item in result.findings if item.rule_id == rule_id)
    assert finding.evidence_files


def test_duplicate_paths_do_not_trigger_large_change() -> None:
    result = evaluate(["app/main.py"] * 20)
    assert result.evaluated_file_count == 1
    assert all(item.rule_id != "large_change" for item in result.findings)


def test_critical_score_is_capped_at_one_hundred() -> None:
    result = evaluate(
        [
            "alembic/versions/next.py",
            "deploy/helm/ai-sre/templates/rbac.yaml",
            "ci/Jenkinsfile",
            "requirements.lock",
            *[f"app/security/change_{index}.py" for index in range(20)],
        ]
    )
    assert len(result.findings) == 6
    assert result.score == 100
    assert result.level == "critical"
