from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EnzymeEntry


def is_fresh(last_refreshed_at: datetime | None, days: int = 15) -> bool:
    if last_refreshed_at is None:
        return False
    return datetime.utcnow() - last_refreshed_at <= timedelta(days=days)


def find_fresh_uniprot_hit(db: Session, uniprot_id: str) -> EnzymeEntry | None:
    entry = db.scalar(select(EnzymeEntry).where(EnzymeEntry.uniprot_id == uniprot_id))
    if entry and is_fresh(entry.last_refreshed_at):
        return entry
    return None
