from datetime import datetime, timedelta

from app.db.models import EnzymeModule, SearchCacheRecord
from app.services.cache import find_fresh_search_cache, is_fresh


def test_is_fresh_rejects_future_timestamp():
    assert is_fresh(datetime.utcnow() + timedelta(seconds=1)) is False


def test_is_fresh_accepts_recent_timestamp():
    assert is_fresh(datetime.utcnow() - timedelta(days=1)) is True


def test_find_fresh_search_cache_returns_recent_matching_record(db_session):
    record = SearchCacheRecord(
        query="P12345",
        normalized_query="P12345",
        query_kind="uniprot",
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        payload_json={"enzyme_entry_id": "enzyme-1"},
        last_refreshed_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(record)
    db_session.commit()

    match = find_fresh_search_cache(
        db_session,
        normalized_query="P12345",
        query_kind="uniprot",
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
    )

    assert match is not None
    assert match.payload_json == {"enzyme_entry_id": "enzyme-1"}


def test_find_fresh_search_cache_rejects_stale_matching_record(db_session):
    record = SearchCacheRecord(
        query="P12345",
        normalized_query="P12345",
        query_kind="uniprot",
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        payload_json={"enzyme_entry_id": "enzyme-1"},
        last_refreshed_at=datetime.utcnow() - timedelta(days=16),
    )
    db_session.add(record)
    db_session.commit()

    match = find_fresh_search_cache(
        db_session,
        normalized_query="P12345",
        query_kind="uniprot",
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
    )

    assert match is None
