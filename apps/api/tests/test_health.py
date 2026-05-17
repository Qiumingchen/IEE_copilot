from fastapi.testclient import TestClient
import pytest

from app.core.config import get_settings
from app.db import session as db_session
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_settings_and_engine():
    get_settings.cache_clear()
    db_session.reset_engine()
    try:
        yield
    finally:
        get_settings.cache_clear()
        db_session.reset_engine()


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "iee-copilot-api"}


def test_health_db_reports_configuration_without_connecting_when_disabled(monkeypatch):
    monkeypatch.setenv("SKIP_DB_HEALTHCHECK", "true")

    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"database": "skipped"}


def test_health_db_skip_does_not_initialize_engine(monkeypatch):
    monkeypatch.setenv("SKIP_DB_HEALTHCHECK", "true")

    response = client.get("/health/db")

    assert response.status_code == 200
    assert db_session._engine is None
