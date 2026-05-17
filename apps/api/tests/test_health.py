from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "iee-copilot-api"}


def test_health_db_reports_configuration_without_connecting_when_disabled(monkeypatch):
    monkeypatch.setenv("SKIP_DB_HEALTHCHECK", "true")
    get_settings.cache_clear()

    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"database": "skipped"}
    get_settings.cache_clear()
