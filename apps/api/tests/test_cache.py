from datetime import datetime, timedelta

from app.services.cache import is_fresh


def test_is_fresh_rejects_future_timestamp():
    assert is_fresh(datetime.utcnow() + timedelta(seconds=1)) is False


def test_is_fresh_accepts_recent_timestamp():
    assert is_fresh(datetime.utcnow() - timedelta(days=1)) is True
