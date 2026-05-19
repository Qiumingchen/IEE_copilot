from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisArtifact,
    EnzymeEntry,
    EnzymeModule,
    ExpressionRecord,
    KineticRecord,
    LiteratureReference,
    MutationRecord,
    PropertyRecord,
    ProteinSequence,
    SearchCacheRecord,
    StructureEntry,
)


DATA_MODULE_SEQUENCE = "sequence"
DATA_MODULE_STRUCTURE = "structure"
DATA_MODULE_PROPERTY = "property"
DATA_MODULE_MUTATION = "mutation"
DATA_MODULE_LITERATURE = "literature"
DATA_MODULE_MSA_CONSERVATION = "msa_conservation_profile"

REFRESHABLE_DATA_MODULES = (
    DATA_MODULE_SEQUENCE,
    DATA_MODULE_STRUCTURE,
    DATA_MODULE_PROPERTY,
    DATA_MODULE_MUTATION,
    DATA_MODULE_LITERATURE,
    DATA_MODULE_MSA_CONSERVATION,
)

MSA_CONSERVATION_ARTIFACT_TYPES = {"msa", "multiple_sequence_alignment", "conservation", "conservation_profile"}


@dataclass(frozen=True)
class DataFreshness:
    module: str
    last_refreshed_at: datetime | None
    is_fresh: bool


def is_fresh(last_refreshed_at: datetime | None, days: int = 15) -> bool:
    if last_refreshed_at is None:
        return False
    now = datetime.utcnow()
    if last_refreshed_at > now:
        return False
    return now - last_refreshed_at <= timedelta(days=days)


def _latest_timestamp(
    db: Session,
    model,
    column,
    enzyme_id: str,
) -> datetime | None:
    return db.scalar(
        select(column)
        .where(model.enzyme_entry_id == enzyme_id)
        .order_by(column.desc())
        .limit(1)
    )


def _latest_of(*timestamps: datetime | None) -> datetime | None:
    present = [timestamp for timestamp in timestamps if timestamp is not None]
    if not present:
        return None
    return max(present)


def _latest_literature_timestamp(db: Session, enzyme_id: str) -> datetime | None:
    reference_ids = set()
    for model in (PropertyRecord, KineticRecord, ExpressionRecord, MutationRecord):
        reference_ids.update(
            reference_id
            for reference_id in db.scalars(
                select(model.reference_id).where(
                    model.enzyme_entry_id == enzyme_id,
                    model.reference_id.is_not(None),
                )
            )
            if reference_id
        )
    if not reference_ids:
        return None
    return db.scalar(
        select(LiteratureReference.created_at)
        .where(LiteratureReference.id.in_(reference_ids))
        .order_by(LiteratureReference.created_at.desc())
        .limit(1)
    )


def data_freshness_report(
    db: Session,
    enzyme_id: str,
    days: int = 15,
) -> dict[str, DataFreshness]:
    timestamps = {
        DATA_MODULE_SEQUENCE: _latest_timestamp(db, ProteinSequence, ProteinSequence.created_at, enzyme_id),
        DATA_MODULE_STRUCTURE: _latest_timestamp(db, StructureEntry, StructureEntry.updated_at, enzyme_id),
        DATA_MODULE_PROPERTY: _latest_of(
            _latest_timestamp(db, PropertyRecord, PropertyRecord.created_at, enzyme_id),
            _latest_timestamp(db, KineticRecord, KineticRecord.created_at, enzyme_id),
            _latest_timestamp(db, ExpressionRecord, ExpressionRecord.created_at, enzyme_id),
        ),
        DATA_MODULE_MUTATION: _latest_timestamp(db, MutationRecord, MutationRecord.created_at, enzyme_id),
        DATA_MODULE_LITERATURE: _latest_literature_timestamp(db, enzyme_id),
        DATA_MODULE_MSA_CONSERVATION: db.scalar(
            select(AnalysisArtifact.created_at)
            .where(
                AnalysisArtifact.enzyme_entry_id == enzyme_id,
                AnalysisArtifact.artifact_type.in_(MSA_CONSERVATION_ARTIFACT_TYPES),
            )
            .order_by(AnalysisArtifact.created_at.desc())
            .limit(1)
        ),
    }
    return {
        module: DataFreshness(
            module=module,
            last_refreshed_at=timestamp,
            is_fresh=is_fresh(timestamp, days=days),
        )
        for module, timestamp in timestamps.items()
    }


def stale_data_modules(db: Session, enzyme_id: str, days: int = 15) -> list[str]:
    report = data_freshness_report(db, enzyme_id, days=days)
    return [module for module in REFRESHABLE_DATA_MODULES if not report[module].is_fresh]


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
