from datetime import datetime, timedelta

from app.db.models import EnzymeEntry, EnzymeFamily, EnzymeModule
from app.services.exact_matching import find_level_one_exact_match
from app.services.query_resolver import QueryKind


def _enzyme_with_ids(db_session, *, uniprot_id: str | None = None, pdb_id: str | None = None) -> EnzymeEntry:
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Local mTGase",
        organism="Streptomyces mobaraensis",
        ec_number="2.3.2.13",
        uniprot_id=uniprot_id,
        pdb_id=pdb_id,
        source="local",
        last_refreshed_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(enzyme)
    db_session.commit()
    return enzyme


def test_level_one_exact_match_finds_same_uniprot_id(db_session):
    enzyme = _enzyme_with_ids(db_session, uniprot_id="P12345")

    match = find_level_one_exact_match(
        db_session,
        query_kind=QueryKind.UNIPROT,
        normalized_query="P12345",
    )

    assert match == enzyme


def test_level_one_exact_match_finds_same_pdb_id(db_session):
    enzyme = _enzyme_with_ids(db_session, pdb_id="1ABC")

    match = find_level_one_exact_match(
        db_session,
        query_kind=QueryKind.PDB,
        normalized_query="1ABC",
    )

    assert match == enzyme


def test_level_one_exact_match_ignores_keyword_queries(db_session):
    _enzyme_with_ids(db_session, uniprot_id="P12345", pdb_id="1ABC")

    match = find_level_one_exact_match(
        db_session,
        query_kind=QueryKind.KEYWORD,
        normalized_query="P12345",
    )

    assert match is None
