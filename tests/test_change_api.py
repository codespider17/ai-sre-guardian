from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import AnalysisRun, AuditEvent, ChangeEvent, EvidenceItem, Service
from app.settings import get_settings

client = TestClient(app)


def payload(repository: str, delivery_id: str) -> dict[str, object]:
    return {
        "delivery_id": delivery_id,
        "repository_full_name": repository,
        "commit_sha": "c" * 40,
        "git_ref": "refs/heads/main",
        "author": "integration-test",
        "title": "exercise deterministic risk evaluation",
        "changed_files": [
            "alembic/versions/next.py",
            "deploy/helm/ai-sre/templates/rbac.yaml",
            "ci/Jenkinsfile",
            "requirements.lock",
            *[f"app/security/change_{index}.py" for index in range(20)],
        ],
    }


def authorization() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().ingest_token}"}


def create_service(repository: str) -> None:
    with SessionLocal() as session:
        session.add(
            Service(
                name=f"service-{uuid4().hex}",
                repository_full_name=repository,
                namespace="ai-sre-system",
                workload_name="ai-sre-guardian",
            )
        )
        session.commit()


def test_change_api_requires_valid_bearer_token() -> None:
    request = payload(f"codespider17/auth-{uuid4().hex}", uuid4().hex)
    assert client.post("/api/v1/changes/evaluate", json=request).status_code == 401
    response = client.post(
        "/api/v1/changes/evaluate",
        json=request,
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_unknown_repository_is_rejected() -> None:
    request = payload(f"codespider17/missing-{uuid4().hex}", uuid4().hex)
    response = client.post(
        "/api/v1/changes/evaluate",
        json=request,
        headers=authorization(),
    )
    assert response.status_code == 404


def test_change_evaluation_persists_analysis_evidence_and_audit() -> None:
    repository = f"codespider17/persist-{uuid4().hex}"
    delivery_id = uuid4().hex
    create_service(repository)
    response = client.post(
        "/api/v1/changes/evaluate",
        json=payload(repository, delivery_id),
        headers=authorization(),
    )
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["status"] == "evaluated"
    assert receipt["risk_score"] == 100
    assert receipt["risk_level"] == "critical"
    assert receipt["finding_count"] == 6

    with SessionLocal() as session:
        analysis = session.get(AnalysisRun, receipt["analysis_run_id"])
        assert analysis is not None
        assert analysis.status == "completed"
        evidence_count = session.scalar(
            select(func.count())
            .select_from(EvidenceItem)
            .where(EvidenceItem.analysis_run_id == analysis.id)
        )
        audit_count = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_id == analysis.id)
        )
        assert evidence_count == 6
        assert audit_count == 1


def test_duplicate_delivery_reuses_original_analysis() -> None:
    repository = f"codespider17/duplicate-{uuid4().hex}"
    delivery_id = uuid4().hex
    create_service(repository)
    request = payload(repository, delivery_id)
    first = client.post(
        "/api/v1/changes/evaluate",
        json=request,
        headers=authorization(),
    )
    second = client.post(
        "/api/v1/changes/evaluate",
        json=request,
        headers=authorization(),
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "evaluated"
    assert second.json()["status"] == "duplicate"
    assert first.json()["analysis_run_id"] == second.json()["analysis_run_id"]

    with SessionLocal() as session:
        change_count = session.scalar(
            select(func.count())
            .select_from(ChangeEvent)
            .where(ChangeEvent.delivery_id == delivery_id)
        )
        analysis_count = session.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .join(ChangeEvent)
            .where(ChangeEvent.delivery_id == delivery_id)
        )
        assert change_count == 1
        assert analysis_count == 1
