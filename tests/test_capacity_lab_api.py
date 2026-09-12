import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import get_settings

client = TestClient(app)


def authorization(token: str | None = None) -> dict[str, str]:
    value = token or get_settings().capacity_lab_token
    return {"X-Capacity-Lab-Token": value}


def test_capacity_work_returns_bounded_result() -> None:
    response = client.post(
        "/api/v1/capacity-lab/work",
        headers=authorization(),
        json={"iterations": 1000, "seed": 7},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["iterations"] == 1000
    assert body["seed"] == 7
    assert isinstance(body["checksum"], int)
    assert body["duration_ms"] >= 0


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_capacity_work_rejects_missing_or_invalid_token(
    token: str | None,
) -> None:
    headers = {} if token is None else authorization(token)
    response = client.post(
        "/api/v1/capacity-lab/work",
        headers=headers,
        json={"iterations": 1000, "seed": 7},
    )
    assert response.status_code == 401


@pytest.mark.parametrize("iterations", [99, 250_001])
def test_capacity_work_rejects_out_of_range_iterations(
    iterations: int,
) -> None:
    response = client.post(
        "/api/v1/capacity-lab/work",
        headers=authorization(),
        json={"iterations": iterations, "seed": 7},
    )
    assert response.status_code == 422


def test_metrics_exposes_capacity_metric_families() -> None:
    client.post(
        "/api/v1/capacity-lab/work",
        headers=authorization(),
        json={"iterations": 1000, "seed": 7},
    )
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "ai_sre_capacity_requests_total" in response.text
    assert "ai_sre_capacity_request_duration_seconds" in response.text
    assert "ai_sre_capacity_active_requests" in response.text


def test_openapi_contains_work_but_hides_metrics() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/capacity-lab/work" in paths
    assert "/metrics" not in paths
