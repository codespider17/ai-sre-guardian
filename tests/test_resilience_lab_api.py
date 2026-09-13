import pytest
from fastapi.testclient import TestClient

from app.api.resilience_lab import reset_rate_limit_state
from app.main import app
from app.settings import get_settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_rate_limit_state() -> None:
    reset_rate_limit_state()


def authorization(token: str | None = None) -> dict[str, str]:
    value = token or get_settings().resilience_lab_token
    return {"X-Resilience-Lab-Token": value}


def test_rate_limit_allows_three_then_returns_429() -> None:
    responses = [
        client.post(
            "/api/v1/resilience-lab/rate-limit",
            headers=authorization(),
            json={"client_id": "test-client"},
        )
        for _ in range(4)
    ]
    assert [response.status_code for response in responses] == [
        200,
        200,
        200,
        429,
    ]
    assert [response.json()["remaining"] for response in responses[:3]] == [
        2,
        1,
        0,
    ]
    assert int(responses[-1].headers["Retry-After"]) >= 1


def test_rate_limit_isolated_by_client_id() -> None:
    for client_id in ("client-a", "client-b"):
        response = client.post(
            "/api/v1/resilience-lab/rate-limit",
            headers=authorization(),
            json={"client_id": client_id},
        )
        assert response.status_code == 200
        assert response.json()["remaining"] == 2


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_endpoints_reject_missing_or_invalid_token(
    token: str | None,
) -> None:
    headers = {} if token is None else authorization(token)
    response = client.post(
        "/api/v1/resilience-lab/degradation",
        headers=headers,
        json={"dependency_available": False},
    )
    assert response.status_code == 401


def test_degradation_uses_dependency_when_available() -> None:
    response = client.post(
        "/api/v1/resilience-lab/degradation",
        headers=authorization(),
        json={"dependency_available": True},
    )
    assert response.status_code == 200
    assert response.json()["response_source"] == "dependency"


def test_degradation_returns_fallback_when_unavailable() -> None:
    response = client.post(
        "/api/v1/resilience-lab/degradation",
        headers=authorization(),
        json={"dependency_available": False},
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "degraded"
    assert response.json()["response_source"] == "fallback"
    assert response.json()["automated_mutation_allowed"] is False


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("rate-limit", {"client_id": "test", "unexpected": True}),
        (
            "degradation",
            {"dependency_available": False, "unexpected": True},
        ),
    ],
)
def test_payloads_reject_extra_fields(
    path: str,
    payload: dict[str, object],
) -> None:
    response = client.post(
        f"/api/v1/resilience-lab/{path}",
        headers=authorization(),
        json=payload,
    )
    assert response.status_code == 422


def test_metrics_exposes_resilience_metric_families() -> None:
    client.post(
        "/api/v1/resilience-lab/degradation",
        headers=authorization(),
        json={"dependency_available": False},
    )
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "ai_sre_resilience_requests_total" in response.text
    assert "ai_sre_resilience_control_events_total" in response.text


def test_openapi_contains_both_resilience_lab_endpoints() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/resilience-lab/rate-limit" in paths
    assert "/api/v1/resilience-lab/degradation" in paths
