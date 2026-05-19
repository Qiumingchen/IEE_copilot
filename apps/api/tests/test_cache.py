from datetime import datetime, timedelta

from app.db.models import (
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    ProteinSequence,
    PropertyRecord,
    SearchCacheRecord,
    StructureEntry,
)
from app.services.cache import (
    DATA_MODULE_MSA_CONSERVATION,
    DATA_MODULE_PROPERTY,
    DATA_MODULE_SEQUENCE,
    DATA_MODULE_STRUCTURE,
    data_freshness_report,
    find_fresh_search_cache,
    is_fresh,
    stale_data_modules,
)


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


def test_data_freshness_report_tracks_each_data_module(db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Fresh sequence stale structure",
        source="local",
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNG",
            mature_sequence="AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNG",
            source="test",
            checksum="fresh-sequence",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
    )
    db_session.add(
        StructureEntry(
            enzyme_entry_id=enzyme.id,
            structure_type="pdb",
            complex_state="apo",
            pdb_id="1ABC",
            source="test",
            created_at=datetime.utcnow() - timedelta(days=16),
            updated_at=datetime.utcnow() - timedelta(days=16),
        )
    )
    db_session.add(
        PropertyRecord(
            enzyme_entry_id=enzyme.id,
            property_type="optimal_temperature",
            value_original="55",
            unit_original="degC",
            created_at=datetime.utcnow() - timedelta(days=2),
        )
    )
    db_session.commit()

    report = data_freshness_report(db_session, enzyme.id)

    assert report[DATA_MODULE_SEQUENCE].is_fresh is True
    assert report[DATA_MODULE_STRUCTURE].is_fresh is False
    assert report[DATA_MODULE_PROPERTY].is_fresh is True
    assert report[DATA_MODULE_MSA_CONSERVATION].is_fresh is False


def test_stale_data_modules_lists_only_modules_that_need_partial_refresh(db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(family_id=family.id, name="Partial refresh target", source="local")
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNG",
            mature_sequence="AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNG",
            source="test",
            checksum="fresh-sequence",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
    )
    db_session.commit()

    modules = stale_data_modules(db_session, enzyme.id)

    assert DATA_MODULE_SEQUENCE not in modules
    assert DATA_MODULE_STRUCTURE in modules
    assert DATA_MODULE_PROPERTY in modules
    assert DATA_MODULE_MSA_CONSERVATION in modules
