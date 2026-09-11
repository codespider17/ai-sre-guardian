from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import Service, SLOEvaluationRecord
from app.settings import get_settings

client = TestClient(app)


def authorization() -> dict[str, str]:
    token = get_settings().ingest_token
    return {"Authorization": f"Bearer {token}"}


def create_service() -> Service:
    token = uuid4().hex
    with SessionLocal() as session:
        service = Service(
            name=f"slo-api-{token}",
            repository_full_name=f"codespider17/slo-api-{token}",
            namespace="ai-sre-system",
            workload_name="ai-sre-guardian",
        )
        session.add(service)
        session.commit()
        session.refresh(service)
        session.expunge(service)
        return service


def policy_payload(service_id: str) -> dict[str, object]:
    return {
        "service_id": service_id,
        "name": "availability-99.9",
        "sli_type": "availability",
        "objective_percent": 99.9,
        "window_minutes": 43_200,
    }


def evaluation_payload() -> dict[str, object]:
    return {
        "sample_key": "sample-001",
        "sample": {
            "total_requests": 1_000_000,
            "successful_requests": 998_700,
            "latency_good_requests": 992_000,
            "saturation_sample_count": 1_000,
            "saturation_good_samples": 950,
            "downtime_minutes": 60,
        },
    }


def create_policy(service: Service) -> dict[str, object]:
    response = client.post(
        "/api/v1/reliability/policies",
        headers=authorization(),
        json=policy_payload(str(service.id)),
    )
    assert response.status_code == 201
    return response.json()


def test_creates_policy_and_persists_evaluation() -> None:
    service = create_service()
    policy = create_policy(service)
    response = client.post(
        (f"/api/v1/reliability/policies/{policy['policy_id']}/evaluations"),
        headers=authorization(),
        json=evaluation_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert policy["status"] == "created"
    assert body["status"] == "evaluated"
    assert body["burn_rate"] == 1.3
    assert body["breached"] is True
    assert body["sla_impact_minutes"] == 16.8

    with SessionLocal() as session:
        count = session.scalar(
            select(func.count(SLOEvaluationRecord.id)).where(
                SLOEvaluationRecord.id == body["evaluation_id"]
            )
        )
    assert count == 1


def test_duplicate_evaluation_reuses_the_same_record() -> None:
    service = create_service()
    policy = create_policy(service)
    url = f"/api/v1/reliability/policies/{policy['policy_id']}/evaluations"
    first = client.post(
        url,
        headers=authorization(),
        json=evaluation_payload(),
    )
    second = client.post(
        url,
        headers=authorization(),
        json=evaluation_payload(),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["status"] == "evaluated"
    assert second.json()["status"] == "duplicate"
    assert first.json()["evaluation_id"] == second.json()["evaluation_id"]


def test_reliability_api_requires_bearer_token() -> None:
    service = create_service()
    response = client.post(
        "/api/v1/reliability/policies",
        json=policy_payload(str(service.id)),
    )
    assert response.status_code == 401


def test_unknown_service_returns_not_found() -> None:
    response = client.post(
        "/api/v1/reliability/policies",
        headers=authorization(),
        json=policy_payload(str(uuid4())),
    )
    assert response.status_code == 404


def test_changed_duplicate_policy_returns_conflict() -> None:
    service = create_service()
    payload = policy_payload(str(service.id))
    first = client.post(
        "/api/v1/reliability/policies",
        headers=authorization(),
        json=payload,
    )
    payload["objective_percent"] = 99.5
    second = client.post(
        "/api/v1/reliability/policies",
        headers=authorization(),
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 409
