from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_checks_database() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
