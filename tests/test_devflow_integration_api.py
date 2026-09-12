from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import AuditEvent, ReleaseObservation, Service
from app.settings import get_settings

client = TestClient(app)


def authorization() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().ingest_token}"}


def create_service() -> Service:
    token = uuid4().hex
    with SessionLocal() as session:
        service = Service(
            name=f"devflow-integration-{token}",
            repository_full_name=f"codespider17/integration-{token}",
            namespace="ai-sre-system",
            workload_name="ai-sre-guardian",
        )
        session.add(service)
        session.commit()
        session.refresh(service)
        session.expunge(service)
        return service


def payload(service_id: str) -> dict[str, object]:
    return {
        "delivery_id": f"integration-{uuid4().hex}",
        "service_id": service_id,
        "pipeline_run_id": str(uuid4()),
        "deployment_id": str(uuid4()),
        "environment": "development",
        "commit_sha": "a" * 40,
        "image_reference": "hb.reg.com/devflow/devflow-api:" + "a" * 40,
        "status": "succeeded",
        "observed_at": datetime.now(UTC).isoformat(),
    }


def test_records_release_and_audit_event() -> None:
    service = create_service()
    response = client.post(
        "/api/v1/integrations/devflow/releases",
        headers=authorization(),
        json=payload(str(service.id)),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "recorded"
    assert body["release_status"] == "succeeded"

    with SessionLocal() as session:
        observation_count = session.scalar(
            select(func.count(ReleaseObservation.id)).where(
                ReleaseObservation.id == body["observation_id"]
            )
        )
        audit_count = session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.entity_id == body["observation_id"],
                AuditEvent.action == "devflow.release_observed",
            )
        )
    assert observation_count == 1
    assert audit_count == 1


def test_duplicate_delivery_reuses_observation() -> None:
    service = create_service()
    request = payload(str(service.id))
    first = client.post(
        "/api/v1/integrations/devflow/releases",
        headers=authorization(),
        json=request,
    )
    second = client.post(
        "/api/v1/integrations/devflow/releases",
        headers=authorization(),
        json=request,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["status"] == "recorded"
    assert second.json()["status"] == "duplicate"
    assert first.json()["observation_id"] == second.json()["observation_id"]


def test_conflicting_delivery_returns_conflict() -> None:
    service = create_service()
    request = payload(str(service.id))
    first = client.post(
        "/api/v1/integrations/devflow/releases",
        headers=authorization(),
        json=request,
    )
    request["status"] = "failed"
    second = client.post(
        "/api/v1/integrations/devflow/releases",
        headers=authorization(),
        json=request,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_integration_requires_bearer_token() -> None:
    service = create_service()
    response = client.post(
        "/api/v1/integrations/devflow/releases",
        json=payload(str(service.id)),
    )
    assert response.status_code == 401


def test_unknown_service_returns_not_found() -> None:
    response = client.post(
        "/api/v1/integrations/devflow/releases",
        headers=authorization(),
        json=payload(str(uuid4())),
    )
    assert response.status_code == 404
