from datetime import datetime, timedelta

from app.db.models import EnzymeEntry, EnzymeFamily, EnzymeModule, ProteinSequence
from app.services.similarity_matching import (
    calculate_ungapped_similarity,
    find_level_two_similarity_match,
)


QUERY_SEQUENCE = "AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNGDKVTVEQSNNG"
SIMILAR_SEQUENCE = "AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNGDKVTVEQSNNG"
LOW_IDENTITY_SEQUENCE = "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"


def _add_sequence(
    db_session,
    *,
    module: EnzymeModule,
    name: str,
    sequence: str,
) -> EnzymeEntry:
    family = EnzymeFamily(module=module, name=f"{module.value} family")
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name=name,
        source="local",
        last_refreshed_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence=sequence,
            mature_sequence=sequence,
            source="test",
            checksum=f"{enzyme.id}-checksum",
        )
    )
    db_session.commit()
    return enzyme


def test_calculate_ungapped_similarity_reports_identity_and_coverage():
    result = calculate_ungapped_similarity(QUERY_SEQUENCE, SIMILAR_SEQUENCE)

    assert result.identity == 1.0
    assert result.coverage == 1.0


def test_level_two_similarity_match_finds_same_module_candidate(db_session):
    enzyme = _add_sequence(
        db_session,
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Similar mTGase",
        sequence=SIMILAR_SEQUENCE,
    )

    match = find_level_two_similarity_match(
        db_session,
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        query_sequence=QUERY_SEQUENCE,
    )

    assert match is not None
    assert match.enzyme == enzyme
    assert match.identity >= 0.4
    assert match.coverage >= 0.7


def test_level_two_similarity_match_ignores_other_modules(db_session):
    _add_sequence(
        db_session,
        module=EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE,
        name="Other module sequence",
        sequence=SIMILAR_SEQUENCE,
    )

    match = find_level_two_similarity_match(
        db_session,
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        query_sequence=QUERY_SEQUENCE,
    )

    assert match is None


def test_level_two_similarity_match_rejects_low_identity(db_session):
    _add_sequence(
        db_session,
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Low identity mTGase",
        sequence=LOW_IDENTITY_SEQUENCE,
    )

    match = find_level_two_similarity_match(
        db_session,
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        query_sequence=QUERY_SEQUENCE,
    )

    assert match is None
