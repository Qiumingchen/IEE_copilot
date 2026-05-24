from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EnzymeEntry
from app.services.query_resolver import QueryKind
from app.services.structure_identifiers import alphafold_identifier_candidates


def find_level_one_exact_match(
    db: Session,
    *,
    query_kind: QueryKind,
    normalized_query: str,
) -> EnzymeEntry | None:
    if query_kind == QueryKind.UNIPROT:
        return db.scalar(select(EnzymeEntry).where(EnzymeEntry.uniprot_id == normalized_query))
    if query_kind == QueryKind.PDB:
        return db.scalar(select(EnzymeEntry).where(EnzymeEntry.pdb_id == normalized_query))
    if query_kind == QueryKind.ALPHAFOLD:
        candidates = alphafold_identifier_candidates(normalized_query)
        return db.scalar(select(EnzymeEntry).where(EnzymeEntry.alphafold_id.in_(candidates)))
    return None
