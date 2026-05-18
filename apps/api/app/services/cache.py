from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EnzymeEntry, EnzymeModule, SearchCacheRecord


def is_fresh(last_refreshed_at: datetime | None, days: int = 15) -> bool:
    if last_refreshed_at is None:
        return False
    now = datetime.utcnow()
    if last_refreshed_at > now:
        return False
    return now - last_refreshed_at <= timedelta(days=days)


def find_fresh_uniprot_hit(db: Session, uniprot_id: str) -> EnzymeEntry | None:
    entry = db.scalar(select(EnzymeEntry).where(EnzymeEntry.uniprot_id == uniprot_id))
    if entry and is_fresh(entry.last_refreshed_at):
        return entry
    return None


def find_search_cache(
    db: Session,
    normalized_query: str,
    query_kind: str,
    module: EnzymeModule | None,
) -> SearchCacheRecord | None:
    return db.scalar(
        select(SearchCacheRecord).where(
            SearchCacheRecord.normalized_query == normalized_query,
            SearchCacheRecord.query_kind == query_kind,
            SearchCacheRecord.module == module,
        )
    )


def find_fresh_search_cache(
    db: Session,
    normalized_query: str,
    query_kind: str,
    module: EnzymeModule | None,
) -> SearchCacheRecord | None:
    record = find_search_cache(db, normalized_query, query_kind, module)
    if record and is_fresh(record.last_refreshed_at):
        return record
    return None
