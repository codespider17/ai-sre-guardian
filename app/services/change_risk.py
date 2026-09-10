from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.schemas_risk import (
    ChangeRiskInput,
    ChangeRiskResult,
    RiskFinding,
    RiskLevel,
)


@dataclass(frozen=True)
class RiskRule:
    rule_id: str
    score: int
    title: str
    explanation: str
    matcher: Callable[[list[str]], list[str]]


def containing(paths: list[str], markers: tuple[str, ...]) -> list[str]:
    return [path for path in paths if any(item in path for item in markers)]


def database(paths: list[str]) -> list[str]:
    return containing(
        paths,
        ("alembic/versions/", "/migrations/", "schema.sql"),
    )


def kubernetes(paths: list[str]) -> list[str]:
    return containing(
        paths,
        ("deploy/helm/", "deploy/kubernetes/", "k8s/", "kubernetes/"),
    )


def pipeline(paths: list[str]) -> list[str]:
    return containing(
        paths,
        ("jenkinsfile", ".github/workflows/", ".gitlab-ci", "ci/"),
    )


def dependency(paths: list[str]) -> list[str]:
    names = {
        "pyproject.toml",
        "poetry.lock",
        "requirements.lock",
        "package.json",
        "package-lock.json",
        "go.mod",
        "go.sum",
        "dockerfile",
    }
    return [path for path in paths if PurePosixPath(path).name in names]


def security(paths: list[str]) -> list[str]:
    return containing(
        paths,
        ("auth", "security", "secret", "rbac", "permission", "credential"),
    )


def large_change(paths: list[str]) -> list[str]:
    return paths if len(paths) >= 20 else []


RISK_RULES = (
    RiskRule(
        "database_migration",
        25,
        "数据库迁移变更",
        "可能带来兼容性、锁表或回滚风险。",
        database,
    ),
    RiskRule(
        "kubernetes_infrastructure",
        20,
        "Kubernetes基础设施变更",
        "可能改变运行资源和发布行为。",
        kubernetes,
    ),
    RiskRule(
        "ci_cd_pipeline",
        15,
        "CI/CD流水线变更",
        "可能改变构建、扫描、发布或回滚顺序。",
        pipeline,
    ),
    RiskRule(
        "dependency_or_image",
        15,
        "依赖或镜像变更",
        "可能引入兼容性和供应链风险。",
        dependency,
    ),
    RiskRule(
        "security_boundary",
        30,
        "安全边界变更",
        "认证、授权或凭据变更需要安全审查。",
        security,
    ),
    RiskRule(
        "large_change",
        20,
        "大规模文件变更",
        "20个及以上文件会扩大验证范围和故障半径。",
        large_change,
    ),
)

RULE_COUNT = len(RISK_RULES)


def score_to_level(score: int) -> RiskLevel:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def evaluate_change_risk(change: ChangeRiskInput) -> ChangeRiskResult:
    paths = sorted(
        {
            str(PurePosixPath(path.strip().replace("\\", "/")))
            .removeprefix("./")
            .lower()
            for path in change.changed_files
            if path.strip()
        }
    )
    findings = [
        RiskFinding(
            rule_id=rule.rule_id,
            score=rule.score,
            title=rule.title,
            explanation=rule.explanation,
            evidence_files=evidence,
        )
        for rule in RISK_RULES
        if (evidence := rule.matcher(paths))
    ]
    score = min(sum(item.score for item in findings), 100)
    return ChangeRiskResult(
        score=score,
        level=score_to_level(score),
        findings=findings,
        evaluated_file_count=len(paths),
    )
