from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import ReleaseObservation, Service
from app.settings import get_settings

client = TestClient(app)


def authorization() -> dict[str, str]:
    token = get_settings().ingest_token
    return {"Authorization": f"Bearer {token}"}


def create_observation(status: str = "succeeded") -> ReleaseObservation:
    token = uuid4().hex
    with SessionLocal() as session:
        service = Service(
            name=f"governance-api-{token}",
            repository_full_name=f"codespider17/governance-api-{token}",
            namespace="ai-sre-system",
            workload_name="ai-sre-guardian",
        )
        session.add(service)
        session.flush()
        observation = ReleaseObservation(
            service_id=service.id,
            delivery_id=f"governance-api-{token}",
            source="devflow",
            source_pipeline_run_id=uuid4(),
            source_deployment_id=uuid4(),
            environment="development",
            commit_sha="c" * 40,
            image_reference="hb.reg.com/devflow/api:" + "c" * 40,
            status=status,
            raw_event={"status": status},
            observed_at=datetime.now(UTC),
        )
        session.add(observation)
        session.commit()
        session.refresh(observation)
        session.expunge(observation)
        return observation


def recommendation_payload(
    observation_id: str,
    *,
    release_status: str = "succeeded",
    risk_level: str = "medium",
    burn_rate: float = 1.3,
    breached: bool = True,
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "signals": {
            "release_status": release_status,
            "risk_level": risk_level,
            "error_budget_burn_rate": burn_rate,
            "slo_breached": breached,
            "evidence_refs": [f"observation:{observation_id}"],
        },
    }


def approval_payload(decision: str = "approved") -> dict[str, str]:
    return {
        "decision": decision,
        "actor": "platform-approver",
        "reason": "reviewed reliability evidence",
    }


def create_recommendation(
    observation: ReleaseObservation,
    **overrides: object,
) -> dict[str, object]:
    payload = recommendation_payload(str(observation.id), **overrides)
    response = client.post(
        "/api/v1/release-governance/recommendations",
        headers=authorization(),
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def test_records_release_recommendation() -> None:
    observation = create_observation()
    body = create_recommendation(observation)
    assert body["status"] == "recorded"
    assert body["decision"] == "manual_review"
    assert body["automated_mutation_allowed"] is False


def test_duplicate_recommendation_reuses_record() -> None:
    observation = create_observation()
    first = create_recommendation(observation)
    second = create_recommendation(observation)
    assert second["status"] == "duplicate"
    assert first["recommendation_id"] == second["recommendation_id"]


def test_recommendation_requires_bearer_token() -> None:
    observation = create_observation()
    response = client.post(
        "/api/v1/release-governance/recommendations",
        json=recommendation_payload(str(observation.id)),
    )
    assert response.status_code == 401


def test_unknown_observation_returns_not_found() -> None:
    response = client.post(
        "/api/v1/release-governance/recommendations",
        headers=authorization(),
        json=recommendation_payload(str(uuid4())),
    )
    assert response.status_code == 404


def test_observation_status_conflict_returns_conflict() -> None:
    observation = create_observation("failed")
    response = client.post(
        "/api/v1/release-governance/recommendations",
        headers=authorization(),
        json=recommendation_payload(str(observation.id)),
    )
    assert response.status_code == 409


def test_records_and_deduplicates_human_decision() -> None:
    observation = create_observation()
    recommendation = create_recommendation(observation)
    url = (
        "/api/v1/release-governance/recommendations/"
        f"{recommendation['recommendation_id']}/decisions"
    )
    first = client.post(
        url,
        headers=authorization(),
        json=approval_payload(),
    )
    second = client.post(
        url,
        headers=authorization(),
        json=approval_payload(),
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["status"] == "recorded"
    assert second.json()["status"] == "duplicate"
    assert first.json()["approval_id"] == second.json()["approval_id"]


def test_unknown_recommendation_returns_not_found() -> None:
    response = client.post(
        (f"/api/v1/release-governance/recommendations/{uuid4()}/decisions"),
        headers=authorization(),
        json=approval_payload(),
    )
    assert response.status_code == 404


def test_blocked_recommendation_cannot_be_approved() -> None:
    observation = create_observation()
    recommendation = create_recommendation(
        observation,
        risk_level="critical",
        burn_rate=0.8,
        breached=False,
    )
    response = client.post(
        (
            "/api/v1/release-governance/recommendations/"
            f"{recommendation['recommendation_id']}/decisions"
        ),
        headers=authorization(),
        json=approval_payload(),
    )
    assert recommendation["decision"] == "block"
    assert response.status_code == 409
