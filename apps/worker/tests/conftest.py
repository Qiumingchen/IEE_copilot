import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def default_to_mock_science_providers(monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "false")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
