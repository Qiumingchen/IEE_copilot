from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
from sqlalchemy import select

from app.db.models import (
    AnalysisJob,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    ExpressionRecord,
    JobStatus,
    KineticRecord,
    LiteratureReference,
    MutationRecord,
    ProteinSequence,
    PropertyRecord,
    SearchCacheRecord,
    StructureEntry,
)
from app.api.routes.enzymes import _ensure_protein_sequence
from app.external.alphafold import AlphaFoldModelMetadata
from app.external.enzyme_data import (
    ExternalEnzymeDataBatch,
    ExternalKineticParameter,
    ExternalLiteratureDatum,
    ExternalMutantRecord,
    ExternalPropertyDatum,
    MockEnzymeDataClient,
)
from app.external.literature import LiteratureMetadata, MockLiteratureClient
from app.external.rcsb import RcsbStructureMetadata
from app.external.uniprot import P81453_FULL_SEQUENCE, P81453_MATURE_SEQUENCE, UniProtEntry, UniProtSearchHit
from app.services.cache import DATA_MODULE_SEQUENCE, DATA_MODULE_STRUCTURE


class EmptyUniProtClient:
    source = "uniprot"

    def search_by_ec(self, ec_number: str, size: int = 5):
        return []

    def search_by_keyword(self, keyword: str, size: int = 5):
        return []

    def search_by_organism(self, organism: str, size: int = 5):
        return []

    def fetch_entry(self, accession: str):
        raise AssertionError("search should not fetch an entry without hits")

    def fetch_fasta(self, accession: str):
        raise AssertionError("search should not fetch FASTA without hits")


def test_seed_mtgase_sequence_repair_updates_old_mock_mature_sequence(db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Microbial transglutaminase",
        organism="Streptomyces mobaraensis",
        ec_number="2.3.2.13",
        source="seed",
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="AEAKLLNDTLLAIGGQ",
            mature_sequence="AEAKLLNDTLLAIGGQ",
            source="seed",
            checksum="old-mock-checksum",
        )
    )
    db_session.commit()

    _ensure_protein_sequence(db_session, enzyme, EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE)

    sequence = db_session.scalar(select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == enzyme.id))
    assert sequence.sequence == P81453_FULL_SEQUENCE
    assert sequence.mature_sequence == P81453_MATURE_SEQUENCE
    assert sequence.checksum != "old-mock-checksum"


def test_mock_mtgase_sequence_repair_updates_old_uniprot_mock_entry(db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Mock microbial transglutaminase",
        organism="Streptomyces mobaraensis",
        ec_number="2.3.2.13",
        uniprot_id="MOCKMTG1",
        source="uniprot_mock",
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="AEAKLLNDTLLAIGGQ",
            mature_sequence="AEAKLLNDTLLAIGGQ",
            source="uniprot_mock",
            checksum="old-uniprot-mock-checksum",
        )
    )
    db_session.commit()

    _ensure_protein_sequence(db_session, enzyme, EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE)

    sequence = db_session.scalar(select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == enzyme.id))
    assert sequence.sequence == P81453_FULL_SEQUENCE
    assert sequence.mature_sequence == P81453_MATURE_SEQUENCE
    assert sequence.checksum != "old-uniprot-mock-checksum"


def test_cached_mock_mtgase_search_repairs_old_uniprot_mock_sequence(
    client,
    db_session,
    monkeypatch,
):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: EmptyUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "cached-mock-searcher@example.com",
            "password": "search-password",
            "display_name": "Cached Mock Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "cached-mock-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Mock microbial transglutaminase",
        organism="Streptomyces mobaraensis",
        ec_number="2.3.2.13",
        uniprot_id="MOCKMTG1",
        source="uniprot_mock",
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="AEAKLLNDTLLAIGGQ",
            mature_sequence="AEAKLLNDTLLAIGGQ",
            source="uniprot_mock",
            checksum="old-cached-mock-checksum",
        )
    )
    db_session.add(
        SearchCacheRecord(
            query="transglutaminase",
            normalized_query="transglutaminase",
            query_kind="keyword",
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            enzyme_entry_id=enzyme.id,
            payload_json={},
            source="uniprot_mock",
            last_refreshed_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "transglutaminase"},
    )

    assert response.status_code == 200
    assert response.json()["cache_status"] == "hit"
    sequence = db_session.scalar(select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == enzyme.id))
    assert sequence.sequence == P81453_FULL_SEQUENCE
    assert sequence.mature_sequence == P81453_MATURE_SEQUENCE
    assert sequence.source == "seed"


def test_enzyme_search_creates_family_profile_job(client, monkeypatch):
    enqueued_job_ids = []

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "searcher@example.com",
            "password": "search-password",
            "display_name": "Search Engineer",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    project_response = client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "MTGase optimization",
            "target_enzyme_module": "MICROBIAL_TRANSGLUTAMINASE_MATURE",
        },
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    search_response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "query": "microbial transglutaminase",
            "project_id": project_id,
        },
    )

    assert search_response.status_code == 200
    body = search_response.json()
    assert body["enzyme"]["name"]
    assert body["job_id"]
    assert body["cache_status"] in {"hit", "miss_refreshed", "stale_refreshed"}
    assert enqueued_job_ids == [body["job_id"]]


def test_enzyme_search_returns_clickable_source_matches(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    class EmptyEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    db_session.add_all(
        [
            EnzymeEntry(
                family_id=family.id,
                name="Microbial transglutaminase A",
                organism="Streptomyces mobaraensis",
                ec_number="2.3.2.13",
                uniprot_id="P81453",
                source="uniprot",
                last_refreshed_at=datetime.utcnow(),
            ),
            EnzymeEntry(
                family_id=family.id,
                name="Microbial transglutaminase B",
                organism="Streptomyces lydicus",
                ec_number="2.3.2.13",
                uniprot_id="Q00001",
                source="curated_literature",
                last_refreshed_at=datetime.utcnow(),
            ),
        ]
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "match-list-searcher@example.com",
            "password": "search-password",
            "display_name": "Match List Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "match-list-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "microbial transglutaminase"},
    )

    assert response.status_code == 200
    matches = response.json()["matches"]
    assert len(matches) >= 2
    assert response.json()["enzyme"]["id"] in {match["id"] for match in matches}
    assert {match["source"] for match in matches} >= {"uniprot", "curated_literature"}


def test_enzyme_search_orders_source_matches_by_reviewed_temperature_and_activity(
    client,
    db_session,
    monkeypatch,
):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Food processing amylases",
    )
    db_session.add(family)
    db_session.flush()
    reviewed = EnzymeEntry(
        family_id=family.id,
        name="Food alpha amylase reviewed",
        organism="Bacillus subtilis",
        ec_number="3.2.1.1",
        uniprot_id="P00691",
        uniprot_reviewed=True,
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    hot = EnzymeEntry(
        family_id=family.id,
        name="Food alpha amylase hot",
        organism="Geobacillus stearothermophilus",
        ec_number="3.2.1.1",
        source="curated_literature",
        last_refreshed_at=datetime.utcnow(),
    )
    active = EnzymeEntry(
        family_id=family.id,
        name="Food alpha amylase active",
        organism="Aspergillus oryzae",
        ec_number="3.2.1.1",
        source="curated_literature",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add_all([active, hot, reviewed])
    db_session.flush()
    db_session.add_all(
        [
            PropertyRecord(
                enzyme_entry_id=hot.id,
                property_type="optimal_temperature",
                value_original="85",
                unit_original="degC",
                value_standardized="85",
                unit_standardized="degC",
                standardization_status="standardized",
            ),
            PropertyRecord(
                enzyme_entry_id=active.id,
                property_type="optimal_temperature",
                value_original="55",
                unit_original="degC",
                value_standardized="55",
                unit_standardized="degC",
                standardization_status="standardized",
            ),
            PropertyRecord(
                enzyme_entry_id=active.id,
                property_type="specific_activity",
                value_original="900",
                unit_original="U/mg",
                value_standardized="900",
                unit_standardized="U/mg",
                standardization_status="standardized",
            ),
        ]
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "ranked-searcher@example.com",
            "password": "search-password",
            "display_name": "Ranked Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "ranked-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "food alpha amylase"},
    )

    assert response.status_code == 200
    matches = response.json()["matches"]
    ordered_ids = [match["id"] for match in matches[:3]]
    assert ordered_ids == [reviewed.id, hot.id, active.id]
    assert matches[0]["uniprot_reviewed"] is True
    assert matches[1]["optimal_temperature"] == 85.0
    assert matches[2]["specific_activity"] == 900.0


def test_enzyme_search_summarizes_available_real_records(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    class EmptyEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Food beta amylases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Food beta amylase record rich",
        organism="Bacillus subtilis",
        ec_number="3.2.1.2",
        uniprot_id="P00002",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add_all(
        [
            PropertyRecord(
                enzyme_entry_id=enzyme.id,
                property_type="optimal_temperature",
                value_original="70",
                unit_original="degC",
                value_standardized="70",
                unit_standardized="degC",
                standardization_status="standardized",
            ),
            KineticRecord(
                enzyme_entry_id=enzyme.id,
                substrate="starch",
                km="1.2",
                kcat="50",
                kcat_km="41.7",
                unit_original="s-1 mM-1",
            ),
            MutationRecord(
                enzyme_entry_id=enzyme.id,
                mutation_string="A10V",
                mutation_positions={"positions": [{"wildtype": "A", "position": 10, "mutant": "V"}]},
            ),
            StructureEntry(
                enzyme_entry_id=enzyme.id,
                structure_type="alphafold_model",
                complex_state="apo",
                pdb_id=None,
                chain_summary={"provenance": {"provider": "alphafold"}},
                ligand_summary=None,
                source="alphafold",
            ),
            ExpressionRecord(
                enzyme_entry_id=enzyme.id,
                expression_host="Escherichia coli",
                expression_level_original="20 mg/L",
                soluble_expression="high",
            ),
        ]
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "record-count-searcher@example.com",
            "password": "search-password",
            "display_name": "Record Count Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "record-count-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "food beta amylase"},
    )

    assert response.status_code == 200
    match = next(item for item in response.json()["matches"] if item["id"] == enzyme.id)
    assert match["record_counts"] == {
        "properties": 1,
        "kinetics": 1,
        "mutations": 1,
        "structures": 1,
        "expression": 1,
    }


def test_enzyme_family_entries_endpoint_lists_same_family_sources(client, db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Food lipases",
    )
    db_session.add(family)
    db_session.flush()
    primary = EnzymeEntry(
        family_id=family.id,
        name="Food lipase Bacillus",
        organism="Bacillus subtilis",
        ec_number="3.1.1.3",
        uniprot_id="LIP001",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    sibling = EnzymeEntry(
        family_id=family.id,
        name="Food lipase Geobacillus",
        organism="Geobacillus stearothermophilus",
        ec_number="3.1.1.3",
        uniprot_id="LIP002",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    other_family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Other enzymes",
    )
    db_session.add(other_family)
    db_session.flush()
    other = EnzymeEntry(
        family_id=other_family.id,
        name="Other enzyme",
        organism="Other organism",
        source="uniprot",
    )
    db_session.add_all([primary, sibling, other])
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "family-list@example.com",
            "password": "search-password",
            "display_name": "Family List",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "family-list@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.get(
        f"/enzymes/{primary.id}/family-entries",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [entry["id"] for entry in body] == [primary.id, sibling.id]
    assert {entry["family_name"] for entry in body} == {"Food lipases"}


def test_real_family_entries_endpoint_filters_unrelated_same_family_records(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Protein-glutamine gamma-glutamyltransferase",
    )
    db_session.add(family)
    db_session.flush()
    primary = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        ec_number="2.3.2.13",
        uniprot_id="P81453",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    related_by_ec = EnzymeEntry(
        family_id=family.id,
        name="Microbial transglutaminase",
        organism="Streptomyces cinnamoneus",
        ec_number="2.3.2.13",
        uniprot_id="Q00001",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    related_by_name = EnzymeEntry(
        family_id=family.id,
        name="Putative transglutaminase",
        organism="Streptomyces sp.",
        ec_number=None,
        uniprot_id="Q00002",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    unrelated = EnzymeEntry(
        family_id=family.id,
        name="High mobility group protein B1",
        organism="Homo sapiens",
        ec_number=None,
        uniprot_id="P09429",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add_all([primary, related_by_ec, related_by_name, unrelated])
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "real-family-filter@example.com",
            "password": "search-password",
            "display_name": "Family Filter",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "real-family-filter@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.get(
        f"/enzymes/{primary.id}/family-entries",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert {entry["id"] for entry in response.json()} == {
        primary.id,
        related_by_ec.id,
        related_by_name.id,
    }


def test_real_provider_search_does_not_create_seed_entry_when_no_real_hit(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: EmptyUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "real-empty-search@example.com",
            "password": "search-password",
            "display_name": "Real Empty Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "real-empty-search@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "no such food enzyme"},
    )

    assert response.status_code == 404
    assert "No real enzyme record found" in response.json()["error"]["message"]
    assert db_session.scalar(select(EnzymeEntry).where(EnzymeEntry.source == "seed")) is None


def test_real_provider_search_ignores_fresh_search_cache(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class RealUniProtClient:
        source = "uniprot"

        def __init__(self):
            self.queries = []

        def search_by_keyword(self, keyword: str, size: int = 5):
            self.queries.append(keyword)
            return [
                UniProtSearchHit(
                    accession="B8DZK4",
                    protein_name="Cellobiose 2-epimerase",
                    organism="Dictyoglomus turgidum",
                    ec_number="5.1.3.11",
                    score=1.0,
                )
            ][:size]

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            return UniProtEntry(
                accession=accession,
                protein_name="Cellobiose 2-epimerase",
                organism="Dictyoglomus turgidum",
                ec_number="5.1.3.11",
                sequence="M" + ("A" * 40),
                mature_sequence="M" + ("A" * 40),
                reviewed=True,
                cross_references={"UniProtKB": accession},
            )

        def fetch_fasta(self, accession: str):
            return f">sp|{accession}|CE_DICD3\nM{'A' * 40}\n"

    uniprot_client = RealUniProtClient()
    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: uniprot_client,
        raising=False,
    )

    cached_family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Cached search family",
    )
    db_session.add(cached_family)
    db_session.flush()
    cached_enzyme = EnzymeEntry(
        family_id=cached_family.id,
        name="Cached unrelated enzyme",
        organism="Cached organism",
        source="uniprot",
        uniprot_id="CACHED1",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(cached_enzyme)
    db_session.flush()
    db_session.add(
        SearchCacheRecord(
            query="cellobiose 2-epimerase",
            normalized_query="cellobiose 2-epimerase",
            query_kind="keyword",
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            enzyme_entry_id=cached_enzyme.id,
            payload_json={},
            source="uniprot",
            last_refreshed_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "real-cache-bypass@example.com",
            "password": "search-password",
            "display_name": "Real Cache Bypass",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "real-cache-bypass@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "cellobiose 2-epimerase"},
    )

    assert response.status_code == 200
    assert uniprot_client.queries[0] == "cellobiose 2-epimerase"
    assert response.json()["enzyme"]["uniprot_id"] == "B8DZK4"
    assert response.json()["enzyme"]["id"] != cached_enzyme.id
    assert response.json()["cache_status"] == "miss_refreshed"


def test_real_provider_search_excludes_mock_and_seed_entries_from_matches(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Food enzyme family",
    )
    db_session.add(family)
    db_session.flush()
    real_enzyme = EnzymeEntry(
        family_id=family.id,
        name="Food lipase real",
        organism="Bacillus realensis",
        source="uniprot",
        uniprot_id="R11111",
        last_refreshed_at=datetime.utcnow(),
    )
    mock_enzyme = EnzymeEntry(
        family_id=family.id,
        name="Food lipase mock",
        organism="Bacillus mockensis",
        source="uniprot_mock",
        uniprot_id="M11111",
        last_refreshed_at=datetime.utcnow(),
    )
    seed_enzyme = EnzymeEntry(
        family_id=family.id,
        name="Food lipase seed",
        organism="Bacillus seedensis",
        source="seed",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add_all([real_enzyme, mock_enzyme, seed_enzyme])
    db_session.commit()

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: EmptyUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "real-match-filter@example.com",
            "password": "search-password",
            "display_name": "Real Match Filter",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "real-match-filter@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "Food lipase real"},
    )

    assert response.status_code == 200
    assert [match["id"] for match in response.json()["matches"]] == [real_enzyme.id]


def test_real_provider_search_does_not_persist_mock_enrichment_data(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class RealUniProtClient:
        source = "uniprot"

        def search_by_keyword(self, keyword: str, size: int = 5):
            return [
                UniProtSearchHit(
                    accession="P81453",
                    protein_name="Microbial transglutaminase",
                    organism="Streptomyces mobaraensis",
                    ec_number="2.3.2.13",
                    score=1.0,
                )
            ][:size]

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            return UniProtEntry(
                accession=accession,
                protein_name="Microbial transglutaminase",
                organism="Streptomyces mobaraensis",
                ec_number="2.3.2.13",
                sequence=P81453_FULL_SEQUENCE,
                mature_sequence=P81453_MATURE_SEQUENCE,
                reviewed=True,
                cross_references={},
            )

        def fetch_fasta(self, accession: str):
            return f">sp|{accession}|MTG_STREMO\n{P81453_FULL_SEQUENCE}\n"

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: RealUniProtClient(),
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_literature_client",
        lambda: MockLiteratureClient(),
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_enzyme_data_client",
        lambda: MockEnzymeDataClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "real-search-no-mock-enrichment@example.com",
            "password": "search-password",
            "display_name": "Real Search No Mock Enrichment",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "real-search-no-mock-enrichment@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "microbial transglutaminase"},
    )

    assert response.status_code == 200
    assert db_session.scalar(select(PropertyRecord)) is None
    assert db_session.scalar(select(KineticRecord)) is None
    assert db_session.scalar(select(MutationRecord)) is None
    assert db_session.scalar(select(LiteratureReference)) is None


def test_real_provider_search_summary_ignores_existing_mock_records(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: EmptyUniProtClient(),
        raising=False,
    )

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Real search family",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Real lipase",
        organism="Bacillus realensis",
        source="uniprot",
        uniprot_id="R22222",
        uniprot_reviewed=True,
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add_all(
        [
            PropertyRecord(
                enzyme_entry_id=enzyme.id,
                property_type="optimal_temperature",
                value_original="99",
                method="enzyme_data_mock",
            ),
            PropertyRecord(
                enzyme_entry_id=enzyme.id,
                property_type="optimal_temperature",
                value_original="55",
                method="europepmc",
            ),
            KineticRecord(
                enzyme_entry_id=enzyme.id,
                substrate="casein",
                km="1.0",
                method="enzyme_data_mock",
            ),
            MutationRecord(
                enzyme_entry_id=enzyme.id,
                mutation_string="A1V",
                assay_condition_summary={"source": "enzyme_data_mock"},
            ),
            StructureEntry(
                enzyme_entry_id=enzyme.id,
                structure_type="alphafold",
                source="alphafold_mock",
            ),
        ]
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "real-summary-filter@example.com",
            "password": "search-password",
            "display_name": "Real Summary Filter",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "real-summary-filter@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "Real lipase"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enzyme"]["optimal_temperature"] == 55.0
    assert body["enzyme"]["record_counts"] == {
        "properties": 1,
        "kinetics": 0,
        "mutations": 0,
        "structures": 0,
        "expression": 0,
    }


def test_real_data_refresh_saves_external_records_without_mock_fallback(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="62",
                    unit_original="degC",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC PMID:123 optimum temperature",
                    reference_title="Real Europe PMC enzyme data",
                    journal="Applied Food Enzymes",
                    year=2025,
                    doi="10.1000/europepmc-data",
                    pubmed_id="123",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_pH",
                    value_original="7.5",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC PMID:123 optimum pH",
                    reference_title="Real Europe PMC enzyme data",
                    journal="Applied Food Enzymes",
                    year=2025,
                    doi="10.1000/europepmc-data",
                    pubmed_id="123",
                )
            ]

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return [
                ExternalKineticParameter(
                    substrate="casein",
                    km="1.8",
                    kcat="24.0",
                    unit_original="mM; s^-1",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC PMID:123 kinetic parameters",
                    reference_title="Real Europe PMC enzyme data",
                    journal="Applied Food Enzymes",
                    year=2025,
                    doi="10.1000/europepmc-data",
                    pubmed_id="123",
                )
            ]

        def fetch_mutants(self, query: str, size: int = 5):
            return [
                ExternalMutantRecord(
                    mutation_string="A10V",
                    effect_summary="Real literature mention: A10V improved thermostability.",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC PMID:123 mutant",
                    reference_title="Real Europe PMC enzyme data",
                    journal="Applied Food Enzymes",
                    year=2025,
                    doi="10.1000/europepmc-data",
                    pubmed_id="123",
                )
            ]

    class RealLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return [
                LiteratureMetadata(
                    title="Real transglutaminase evidence",
                    journal="Food Enzyme Reports",
                    year=2025,
                    doi="10.1000/real-refresh",
                    source=self.source,
                )
            ]

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: RealLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Real microbial transglutaminase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "real-data-refresh@example.com",
            "password": "search-password",
            "display_name": "Real Data Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "real-data-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] == {"references": 2, "properties": 2, "kinetics": 1, "mutations": 1, "structures": 0}
    assert body["sources"] == ["crossref", "europepmc"]

    properties = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    kinetics = db_session.scalars(select(KineticRecord).where(KineticRecord.enzyme_entry_id == enzyme.id)).all()
    mutations = db_session.scalars(select(MutationRecord).where(MutationRecord.enzyme_entry_id == enzyme.id)).all()
    references = db_session.scalars(select(LiteratureReference)).all()
    assert {record.method for record in properties} == {"europepmc"}
    assert kinetics[0].method == "europepmc"
    assert mutations[0].assay_condition_summary["source"] == "europepmc"
    europepmc_reference = next(reference for reference in references if reference.source == "europepmc")
    assert {record.reference_id for record in properties} == {europepmc_reference.id}
    assert kinetics[0].reference_id == europepmc_reference.id
    assert mutations[0].reference_id == europepmc_reference.id


def test_real_data_refresh_persists_extracted_assay_methods(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class BatchRealDataClient:
        source = "europepmc"

        def fetch_enzyme_records(self, query: str, size: int = 5, progress_callback=None):
            return ExternalEnzymeDataBatch(
                property_data=[
                    SimpleNamespace(
                        property_type="specific_activity",
                        value_original="125",
                        unit_original="U/mg",
                        substrate="lactose",
                        assay_temperature="80",
                        assay_pH="7.5",
                        organism="Dictyoglomus turgidum",
                        source="europepmc",
                        evidence="Specific activity toward lactose was 125 U/mg using the DNS assay.",
                        reference_title="Method rich cellobiose epimerase characterization",
                        journal="Applied Microbiology and Biotechnology",
                        year=2012,
                        doi="10.1000/method-rich-ce",
                        pubmed_id="24100573",
                        method="DNS assay",
                    )
                ],
                kinetic_parameters=[
                    SimpleNamespace(
                        substrate="lactose",
                        km="1.2",
                        kcat="42",
                        kcat_km=None,
                        unit_original="Km:mM; kcat:s^-1",
                        assay_temperature="80",
                        assay_pH="7.5",
                        organism="Dictyoglomus turgidum",
                        source="europepmc",
                        evidence="The Km value for lactose was 1.2 mM and kcat value was 42 s^-1, determined by HPLC.",
                        reference_title="Method rich cellobiose epimerase characterization",
                        journal="Applied Microbiology and Biotechnology",
                        year=2012,
                        doi="10.1000/method-rich-ce",
                        pubmed_id="24100573",
                        method="HPLC",
                    )
                ],
                mutant_records=[
                    SimpleNamespace(
                        mutation_string="A123V",
                        effect_summary="A123V increased thermostability.",
                        property_delta={"optimal_temperature": "+5 degC"},
                        substrate="lactose",
                        organism="Dictyoglomus turgidum",
                        source="europepmc",
                        evidence="A123V increased thermostability in a thermal shift assay.",
                        reference_title="Method rich cellobiose epimerase characterization",
                        journal="Applied Microbiology and Biotechnology",
                        year=2012,
                        doi="10.1000/method-rich-ce",
                        pubmed_id="24100573",
                        method="thermal shift assay",
                        assay_temperature="80",
                        assay_pH="7.5",
                    )
                ],
                sources=["europepmc"],
            )

        def fetch_opt_temperature(self, query: str, size: int = 5):
            raise AssertionError("batch client should be used")

        def fetch_opt_pH(self, query: str, size: int = 5):
            raise AssertionError("batch client should be used")

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            raise AssertionError("batch client should be used")

        def fetch_mutants(self, query: str, size: int = 5):
            raise AssertionError("batch client should be used")

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: BatchRealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Cellobiose epimerases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Cellobiose 2-epimerase",
        organism="Dictyoglomus turgidum",
        source="uniprot",
        uniprot_id="B8DZK4",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "method-real-data@example.com",
            "password": "search-password",
            "display_name": "Method Real Data",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "method-real-data@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    property_record = db_session.scalar(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id))
    kinetic_record = db_session.scalar(select(KineticRecord).where(KineticRecord.enzyme_entry_id == enzyme.id))
    mutation_record = db_session.scalar(select(MutationRecord).where(MutationRecord.enzyme_entry_id == enzyme.id))
    assert property_record.method == "DNS assay"
    assert kinetic_record.method == "HPLC"
    assert mutation_record.assay_condition_summary["method"] == "thermal shift assay"
    assert mutation_record.assay_condition_summary["assay_temperature"] == "80"
    assert mutation_record.assay_condition_summary["assay_pH"] == "7.5"


def test_real_data_refresh_backfills_existing_mutation_assay_conditions(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class BatchRealDataClient:
        source = "europepmc"

        def fetch_enzyme_records(self, query: str, size: int = 5, progress_callback=None):
            return ExternalEnzymeDataBatch(
                mutant_records=[
                    SimpleNamespace(
                        mutation_string="A123V",
                        effect_summary="A123V increased thermostability.",
                        property_delta={"optimal_temperature": "+5 degC"},
                        substrate="lactose",
                        organism="Dictyoglomus turgidum",
                        source="europepmc",
                        evidence="A123V increased thermostability at pH 7.5 and 80 degC using a thermal shift assay.",
                        reference_title="Mutation assay context",
                        journal="Applied Microbiology and Biotechnology",
                        year=2012,
                        doi="10.1000/mutation-context",
                        pubmed_id="24100573",
                        method="thermal shift assay",
                        assay_temperature="80",
                        assay_pH="7.5",
                    )
                ],
                sources=["europepmc"],
            )

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: BatchRealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Cellobiose epimerases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Cellobiose 2-epimerase",
        organism="Dictyoglomus turgidum",
        source="uniprot",
        uniprot_id="B8DZK4",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        MutationRecord(
            enzyme_entry_id=enzyme.id,
            mutation_string="A123V",
            effect_summary="A123V increased thermostability.",
            property_delta={"optimal_temperature": "+5 degC"},
            substrate="lactose",
            assay_condition_summary={"source": "old_literature"},
        )
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "mutation-backfill@example.com",
            "password": "search-password",
            "display_name": "Mutation Backfill",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "mutation-backfill@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    mutations = db_session.scalars(select(MutationRecord).where(MutationRecord.enzyme_entry_id == enzyme.id)).all()
    assert len(mutations) == 1
    summary = mutations[0].assay_condition_summary
    assert summary["evidence"].startswith("A123V increased thermostability")
    assert summary["method"] == "thermal shift assay"
    assert summary["assay_temperature"] == "80"
    assert summary["assay_pH"] == "7.5"


def test_real_data_refresh_prefers_batch_external_records(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    calls = []

    class BatchRealDataClient:
        source = "europepmc"

        def fetch_enzyme_records(self, query: str, size: int = 5, progress_callback=None):
            calls.append(("batch", query))
            if progress_callback is not None:
                progress_callback(
                    {
                        "candidate_articles": 2,
                        "articles_scanned": 1,
                        "filtered_articles": 1,
                        "found_records": 2,
                        "stage": "extracting candidate literature",
                    }
                )
            return ExternalEnzymeDataBatch(
                property_data=[
                    ExternalPropertyDatum(
                        property_type="optimal_temperature",
                        value_original="61",
                        unit_original="degC",
                        organism="Streptomyces mobaraensis",
                        source=self.source,
                        evidence="Europe PMC PMID:123 optimum temperature",
                        reference_title="Relevant enzyme paper",
                        pubmed_id="123",
                    ),
                    ExternalPropertyDatum(
                        property_type="substrate_reaction_scope",
                        value_original="epimerizes and isomerizes beta-1,4-gluco-oligosaccharides",
                        organism="Streptomyces mobaraensis",
                        source=self.source,
                        evidence="Europe PMC PMID:123 substrate and reaction scope",
                        reference_title="Relevant enzyme paper",
                        pubmed_id="123",
                    )
                ],
                kinetic_parameters=[
                    ExternalKineticParameter(
                        substrate="casein",
                        km="1.8",
                        organism="Streptomyces mobaraensis",
                        source=self.source,
                        evidence="Europe PMC PMID:123 Km",
                        reference_title="Relevant enzyme paper",
                        pubmed_id="123",
                    )
                ],
                sources=["europepmc"],
            )

        def fetch_opt_temperature(self, query: str, size: int = 5):
            raise AssertionError("batch real-data refresh should not fan out through property searches")

        def fetch_opt_pH(self, query: str, size: int = 5):
            raise AssertionError("batch real-data refresh should not fan out through pH searches")

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            raise AssertionError("batch real-data refresh should not fan out through kinetic searches")

        def fetch_mutants(self, query: str, size: int = 5):
            raise AssertionError("batch real-data refresh should not fan out through mutant searches")

    class RealLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: BatchRealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: RealLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Real microbial transglutaminase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "batch-real-data-refresh@example.com",
            "password": "search-password",
            "display_name": "Batch Real Data Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "batch-real-data-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["properties"] == 2
    assert response.json()["created"]["kinetics"] == 1
    assert calls == [("batch", "Real microbial transglutaminase Streptomyces mobaraensis P81453")]
    properties = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    kinetics = db_session.scalars(select(KineticRecord).where(KineticRecord.enzyme_entry_id == enzyme.id)).all()
    assert {record.property_type for record in properties} == {"optimal_temperature", "substrate_reaction_scope"}
    assert {record.method for record in properties} == {"europepmc"}
    assert kinetics[0].method == "europepmc"


def test_real_data_refresh_links_relevant_literature_without_extractable_values(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class BatchDataClient:
        source = "europepmc"

        def fetch_enzyme_records(self, query: str, size: int = 5, progress_callback=None):
            return ExternalEnzymeDataBatch(
                literature_references=[
                    ExternalLiteratureDatum(
                        organism="Dictyoglomus turgidum",
                        source="europepmc",
                        evidence=(
                            "Acta Crystallographica Section F 2013 pmid:24100573 | "
                            "Evidence: Cellobiose 2-epimerase from Dictyoglomus turgidum was crystallized."
                        ),
                        reference_title=(
                            "Expression, crystallization and preliminary X-ray crystallographic analysis "
                            "of cellobiose 2-epimerase from Dictyoglomus turgidum DSM 6724"
                        ),
                        journal="Acta Crystallographica Section F",
                        year=2013,
                        pubmed_id="24100573",
                    )
                ],
                sources=["europepmc"],
            )

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: BatchDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Cellobiose 2-epimerases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Cellobiose 2-epimerase",
        organism="Dictyoglomus turgidum",
        source="uniprot",
        uniprot_id="B8DZK4",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "linked-literature-refresh@example.com",
            "password": "search-password",
            "display_name": "Linked Literature Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "linked-literature-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["references"] == 1
    assert db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all() == []

    references_response = client.get(
        f"/enzymes/{enzyme.id}/references",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert references_response.status_code == 200
    assert references_response.json()[0]["pubmed_id"] == "24100573"
    assert "cellobiose 2-epimerase" in references_response.json()[0]["title"].lower()


def test_real_data_refresh_attaches_relevant_literature_when_organism_is_missing_but_title_matches(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class BatchDataClient:
        source = "europepmc"

        def fetch_enzyme_records(self, query: str, size: int = 5, progress_callback=None):
            return ExternalEnzymeDataBatch(
                literature_references=[
                    ExternalLiteratureDatum(
                        organism="Dictyoglomus turgidum",
                        source="europepmc",
                        evidence="Evidence: Cellobiose 2-epimerase from Dictyoglomus turgidum was crystallized.",
                        reference_title=(
                            "Expression, crystallization and preliminary X-ray crystallographic analysis "
                            "of cellobiose 2-epimerase from Dictyoglomus turgidum DSM 6724"
                        ),
                        journal="Acta Crystallographica Section F",
                        year=2013,
                        pubmed_id="24100573",
                    ),
                    ExternalLiteratureDatum(
                        organism=None,
                        source="europepmc",
                        evidence=(
                            "Evidence: Characterization of a recombinant cellobiose 2-epimerase "
                            "from Dictyoglomus turgidum that epimerizes gluco-oligosaccharides."
                        ),
                        reference_title=(
                            "Characterization of a recombinant cellobiose 2-epimerase "
                            "from Dictyoglomus turgidum that epimerizes and isomerizes "
                            "beta-1,4- and alpha-1,4-gluco-oligosaccharides"
                        ),
                        journal="Applied Microbiology and Biotechnology",
                        year=2012,
                        doi="10.1007/s00253-012-4002-5",
                    ),
                ],
                sources=["europepmc"],
            )

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: BatchDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Cellobiose 2-epimerases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Cellobiose 2-epimerase",
        organism="Dictyoglomus turgidum (strain DSM 6724 / Z-1310)",
        source="uniprot",
        uniprot_id="B8DZK4",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "fallback-literature-refresh@example.com",
            "password": "search-password",
            "display_name": "Fallback Literature Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "fallback-literature-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"]["references"] == 2
    assert not any("no organism was extracted" in warning for warning in body["warnings"])

    references_response = client.get(
        f"/enzymes/{enzyme.id}/references",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert references_response.status_code == 200
    titles = [reference["title"] for reference in references_response.json()]
    assert any("Expression, crystallization" in title for title in titles)
    assert any("Characterization of a recombinant cellobiose 2-epimerase" in title for title in titles)


def test_real_data_refresh_skips_weak_literature_records_without_organism(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class AmbiguousDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="70",
                    unit_original="degC",
                    source=self.source,
                    evidence="Europe PMC abstract did not identify organism",
                    reference_title="Ambiguous enzyme paper",
                    pubmed_id="999",
                ),
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="68",
                    unit_original="degC",
                    source="openalex",
                    evidence="OpenAlex abstract did not identify organism",
                    reference_title="Ambiguous OpenAlex enzyme paper",
                    doi="10.1000/ambiguous-openalex",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return [
                ExternalKineticParameter(
                    substrate="casein",
                    km="3.0",
                    source="pubmed",
                    evidence="PubMed abstract did not identify organism",
                    reference_title="Ambiguous kinetic paper",
                    pubmed_id="998",
                ),
                ExternalKineticParameter(
                    substrate="gelatin",
                    km="2.0",
                    source="semanticscholar",
                    evidence="Semantic Scholar abstract did not identify organism",
                    reference_title="Ambiguous Semantic Scholar kinetic paper",
                    doi="10.1000/ambiguous-semanticscholar",
                )
            ]

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: AmbiguousDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Real microbial transglutaminase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "ambiguous-real-data@example.com",
            "password": "search-password",
            "display_name": "Ambiguous Real Data",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "ambiguous-real-data@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] == {"references": 0, "properties": 0, "kinetics": 0, "mutations": 0, "structures": 0}
    assert any("no organism was extracted" in warning for warning in body["warnings"])
    assert db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all() == []
    assert db_session.scalars(select(KineticRecord).where(KineticRecord.enzyme_entry_id == enzyme.id)).all() == []


def test_real_data_refresh_attaches_value_records_without_organism_when_context_matches(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class ContextualDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="80",
                    unit_original="degC",
                    source=self.source,
                    evidence=(
                        "Applied Microbiology and Biotechnology 2012 doi:10.1007/s00253-012-4002-5 "
                        "pmid:22488279 | Evidence: The recombinant cellobiose 2-epimerase from "
                        "Dictyoglomus turgidum DSM 6724 showed maximal activity at 80 degC."
                    ),
                    reference_title=(
                        "Characterization of a recombinant cellobiose 2-epimerase from "
                        "Dictyoglomus turgidum that epimerizes and isomerizes beta-1,4- and "
                        "alpha-1,4-gluco-oligosaccharides"
                    ),
                    journal="Applied Microbiology and Biotechnology",
                    year=2012,
                    doi="10.1007/s00253-012-4002-5",
                    pubmed_id="22488279",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return [
                ExternalKineticParameter(
                    substrate="cellobiose",
                    km="1.8",
                    unit_original="mM",
                    source=self.source,
                    evidence=(
                        "Applied Microbiology and Biotechnology 2012 doi:10.1007/s00253-012-4002-5 "
                        "pmid:22488279 | Evidence: The recombinant cellobiose 2-epimerase from "
                        "Dictyoglomus turgidum DSM 6724 showed a Km value of 1.8 mM for cellobiose."
                    ),
                    reference_title=(
                        "Characterization of a recombinant cellobiose 2-epimerase from "
                        "Dictyoglomus turgidum that epimerizes and isomerizes beta-1,4- and "
                        "alpha-1,4-gluco-oligosaccharides"
                    ),
                    journal="Applied Microbiology and Biotechnology",
                    year=2012,
                    doi="10.1007/s00253-012-4002-5",
                    pubmed_id="22488279",
                )
            ]

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: ContextualDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Cellobiose 2-epimerases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Cellobiose 2-epimerase",
        organism="Dictyoglomus turgidum (strain DSM 6724 / Z-1310)",
        source="uniprot",
        uniprot_id="B8DZK4",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "contextual-real-data@example.com",
            "password": "search-password",
            "display_name": "Contextual Real Data",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "contextual-real-data@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"]["properties"] == 1
    assert body["created"]["kinetics"] == 1
    assert not any("no organism was extracted" in warning for warning in body["warnings"])

    property_records = db_session.scalars(
        select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)
    ).all()
    kinetic_records = db_session.scalars(
        select(KineticRecord).where(KineticRecord.enzyme_entry_id == enzyme.id)
    ).all()

    assert property_records[0].value_original == "80"
    assert property_records[0].evidence_text is not None
    assert "Dictyoglomus turgidum DSM 6724 showed maximal activity at 80 degC" in property_records[0].evidence_text
    assert kinetic_records[0].substrate == "cellobiose"
    assert kinetic_records[0].km == "1.8"
    assert kinetic_records[0].evidence_text is not None
    assert "Km value of 1.8 mM for cellobiose" in kinetic_records[0].evidence_text


def test_real_data_refresh_routes_external_records_to_matching_family_organism(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class OrganismSpecificDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="60",
                    unit_original="degC",
                    organism="Bacillus licheniformis DSM 13",
                    source=self.source,
                    evidence="Europe PMC Bacillus licheniformis DSM 13 optimum temperature",
                    reference_title="Bacillus licheniformis transglutaminase",
                    journal="Food Enzymes",
                    year=2024,
                    doi="10.1000/bacillus-lgtgase",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return [
                ExternalKineticParameter(
                    substrate="casein",
                    km="2.0",
                    organism="Bacillus licheniformis DSM 13",
                    source=self.source,
                    evidence="Europe PMC Bacillus licheniformis DSM 13 Km",
                    reference_title="Bacillus licheniformis transglutaminase",
                    journal="Food Enzymes",
                    year=2024,
                    doi="10.1000/bacillus-lgtgase",
                )
            ]

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: OrganismSpecificDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Protein-glutamine gamma-glutamyltransferase",
    )
    db_session.add(family)
    db_session.flush()
    streptomyces = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        ec_number="2.3.2.13",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    bacillus = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Bacillus licheniformis",
        ec_number="2.3.2.13",
        source="uniprot",
        uniprot_id="A0A415J715",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add_all([streptomyces, bacillus])
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "organism-routing@example.com",
            "password": "search-password",
            "display_name": "Organism Routing",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "organism-routing@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{streptomyces.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["properties"] == 1
    assert response.json()["created"]["kinetics"] == 1
    streptomyces_properties = db_session.scalars(
        select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == streptomyces.id)
    ).all()
    bacillus_properties = db_session.scalars(
        select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == bacillus.id)
    ).all()
    bacillus_kinetics = db_session.scalars(
        select(KineticRecord).where(KineticRecord.enzyme_entry_id == bacillus.id)
    ).all()
    assert streptomyces_properties == []
    assert [(record.property_type, record.value_original) for record in bacillus_properties] == [
        ("optimal_temperature", "60")
    ]
    assert bacillus_kinetics[0].km == "2.0"


def test_real_data_refresh_skips_genus_only_external_literature_organism(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class GenusOnlyDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="60",
                    unit_original="degC",
                    organism="Bacillus",
                    source=self.source,
                    evidence="Europe PMC Bacillus optimum temperature without species",
                    reference_title="Genus-only Bacillus enzyme paper",
                    journal="Food Enzymes",
                    year=2024,
                    doi="10.1000/genus-only-bacillus",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: GenusOnlyDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Protein-glutamine gamma-glutamyltransferase",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Bacillus subtilis",
        source="uniprot",
        uniprot_id="Q00000",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "genus-only-routing@example.com",
            "password": "search-password",
            "display_name": "Genus Only Routing",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "genus-only-routing@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"]["properties"] == 0
    assert any("Bacillus" in warning for warning in body["warnings"])
    assert db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all() == []


def test_real_data_refresh_skips_unspecified_species_external_literature_organism(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class UnspecifiedSpeciesDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="62",
                    unit_original="degC",
                    organism="Bacillus sp.",
                    source=self.source,
                    evidence="Europe PMC Bacillus sp. optimum temperature without species",
                    reference_title="Unspecified Bacillus species enzyme paper",
                    journal="Food Enzymes",
                    year=2024,
                    doi="10.1000/bacillus-sp-only",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: UnspecifiedSpeciesDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Protein-glutamine gamma-glutamyltransferase",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Bacillus subtilis",
        source="uniprot",
        uniprot_id="Q00000",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "unspecified-species-routing@example.com",
            "password": "search-password",
            "display_name": "Unspecified Species Routing",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "unspecified-species-routing@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"]["properties"] == 0
    assert any("Bacillus sp." in warning for warning in body["warnings"])
    assert db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all() == []


def test_real_data_refresh_routes_abbreviated_external_literature_organism(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class AbbreviatedOrganismDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="61",
                    unit_original="degC",
                    organism="B. subtilis",
                    source=self.source,
                    evidence="Europe PMC B. subtilis optimum temperature",
                    reference_title="Abbreviated Bacillus subtilis enzyme paper",
                    journal="Food Enzymes",
                    year=2024,
                    doi="10.1000/abbreviated-b-subtilis",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr(
        "app.api.routes.enzymes.get_enzyme_data_client", lambda: AbbreviatedOrganismDataClient()
    )
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Protein-glutamine gamma-glutamyltransferase",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Bacillus subtilis",
        source="uniprot",
        uniprot_id="Q00000",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "abbreviated-organism-routing@example.com",
            "password": "search-password",
            "display_name": "Abbreviated Organism Routing",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "abbreviated-organism-routing@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["properties"] == 1
    records = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    assert [(record.property_type, record.value_original) for record in records] == [
        ("optimal_temperature", "61")
    ]


def test_real_data_refresh_reports_multiple_enzyme_data_sources(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class MultiSourceDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="52",
                    unit_original="degC",
                    source="europepmc",
                    evidence="Europe PMC optimum temperature",
                    reference_title="Europe PMC enzyme paper",
                    journal="Applied Enzymology",
                    year=2024,
                    doi="10.1000/europepmc-source",
                ),
                ExternalPropertyDatum(
                    property_type="optimal_pH",
                    value_original="8.0",
                    source="pubmed",
                    evidence="PubMed optimum pH",
                    reference_title="PubMed enzyme paper",
                    journal="Journal of Enzymes",
                    year=2023,
                    pubmed_id="45678901",
                ),
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_specific_activity(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return [
                ExternalKineticParameter(
                    substrate="CBZ-Gln-Gly",
                    km="2.4",
                    kcat="31",
                    source="sabiork",
                    evidence="SABIO-RK EntryID 12345 pmid:28193333",
                    reference_title="SABIO-RK kinetic law",
                    pubmed_id="28193333",
                )
            ]

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: MultiSourceDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Food enzymes",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Food enzyme",
        organism="Bacillus subtilis",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "multi-source-refresh@example.com",
            "password": "search-password",
            "display_name": "Multi Source Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "multi-source-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert "europepmc" in response.json()["sources"]
    assert "pubmed" in response.json()["sources"]
    assert "sabiork" in response.json()["sources"]


def test_real_data_refresh_backfills_reference_for_existing_real_property(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="50",
                    unit_original="degC",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC PMID:28193333 optimum temperature",
                    reference_title="Characterization of microbial transglutaminase",
                    journal="Enzyme and Microbial Technology",
                    year=2017,
                    doi="10.1016/j.enzmictec.2017.01.003",
                    pubmed_id="28193333",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        PropertyRecord(
            enzyme_entry_id=enzyme.id,
            property_type="optimal_temperature",
            value_original="50",
            unit_original="degC",
            method="europepmc",
            reference_id=None,
        )
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "real-data-backfill@example.com",
            "password": "search-password",
            "display_name": "Real Data Backfill",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "real-data-backfill@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["properties"] == 0
    assert response.json()["created"]["references"] == 1
    properties = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    references = db_session.scalars(select(LiteratureReference)).all()
    assert len(properties) == 1
    assert properties[0].reference_id == references[0].id


def test_real_data_refresh_keeps_same_property_value_with_different_units(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_specific_activity(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="specific_activity",
                    value_original="12",
                    unit_original="U/mg",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC specific activity per mg",
                    reference_title="Specific activity per mg",
                    doi="10.1000/activity-per-mg",
                ),
                ExternalPropertyDatum(
                    property_type="specific_activity",
                    value_original="12",
                    unit_original="U/mL",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC volumetric activity",
                    reference_title="Specific activity per ml",
                    doi="10.1000/activity-per-ml",
                ),
            ]

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "property-unit-distinct@example.com",
            "password": "search-password",
            "display_name": "Property Unit Distinct",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "property-unit-distinct@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["properties"] == 2
    properties = db_session.scalars(
        select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)
    ).all()
    assert sorted(record.unit_original for record in properties) == ["U/mL", "U/mg"]


def test_real_data_refresh_keeps_same_kinetic_values_with_different_units(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return [
                ExternalKineticParameter(
                    substrate="casein",
                    km="1.2",
                    unit_original="mM",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC Km in mM",
                    reference_title="Km in mM",
                    doi="10.1000/km-mm",
                ),
                ExternalKineticParameter(
                    substrate="casein",
                    km="1.2",
                    unit_original="uM",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC Km in uM",
                    reference_title="Km in uM",
                    doi="10.1000/km-um",
                ),
            ]

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "kinetic-unit-distinct@example.com",
            "password": "search-password",
            "display_name": "Kinetic Unit Distinct",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "kinetic-unit-distinct@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["kinetics"] == 2
    kinetics = db_session.scalars(
        select(KineticRecord).where(KineticRecord.enzyme_entry_id == enzyme.id)
    ).all()
    assert sorted(record.unit_original for record in kinetics) == ["mM", "uM"]


def test_real_data_refresh_keeps_same_mutation_for_different_substrates(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return [
                ExternalMutantRecord(
                    mutation_string="S2P",
                    effect_summary="Improved activity on gelatin",
                    property_delta={"specific_activity_fold_change": 1.8},
                    substrate="gelatin",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC S2P gelatin activity",
                    reference_title="Substrate-specific mutant data",
                    journal="Enzyme and Microbial Technology",
                    year=2024,
                    doi="10.1000/s2p-gelatin",
                )
            ]

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        MutationRecord(
            enzyme_entry_id=enzyme.id,
            mutation_string="S2P",
            effect_summary="Improved activity on casein",
            property_delta={"specific_activity_fold_change": 1.2},
            substrate="casein",
        )
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "mutation-substrate-refresh@example.com",
            "password": "search-password",
            "display_name": "Mutation Substrate Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "mutation-substrate-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["mutations"] == 1
    mutations = db_session.scalars(select(MutationRecord).where(MutationRecord.enzyme_entry_id == enzyme.id)).all()
    assert {(record.mutation_string, record.substrate) for record in mutations} == {
        ("S2P", "casein"),
        ("S2P", "gelatin"),
    }


def test_real_data_refresh_keeps_same_mutation_substrate_for_different_property_delta(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return [
                ExternalMutantRecord(
                    mutation_string="S2P",
                    effect_summary="Improved optimal temperature on casein assay",
                    property_delta={"optimal_temperature_delta_degC": 5},
                    substrate="casein",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC S2P casein thermostability",
                    reference_title="Property-specific mutant data",
                    journal="Enzyme and Microbial Technology",
                    year=2024,
                    doi="10.1000/s2p-casein-thermostability",
                )
            ]

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        MutationRecord(
            enzyme_entry_id=enzyme.id,
            mutation_string="S2P",
            effect_summary="Improved activity on casein",
            property_delta={"specific_activity_fold_change": 1.2},
            substrate="casein",
        )
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "mutation-property-refresh@example.com",
            "password": "search-password",
            "display_name": "Mutation Property Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "mutation-property-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["mutations"] == 1
    mutations = db_session.scalars(select(MutationRecord).where(MutationRecord.enzyme_entry_id == enzyme.id)).all()
    assert {tuple(sorted((record.property_delta or {}).keys())) for record in mutations} == {
        ("optimal_temperature_delta_degC",),
        ("specific_activity_fold_change",),
    }


def test_real_data_refresh_treats_null_and_empty_mutation_delta_as_duplicate(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return [
                ExternalMutantRecord(
                    mutation_string="S2P",
                    effect_summary="Reported mutation without structured delta",
                    property_delta={},
                    substrate="casein",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC S2P casein mutation mention",
                    reference_title="Unstructured mutant data",
                    journal="Enzyme and Microbial Technology",
                    year=2024,
                    doi="10.1000/s2p-casein-unstructured",
                )
            ]

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        MutationRecord(
            enzyme_entry_id=enzyme.id,
            mutation_string="S2P",
            effect_summary="Legacy mutation without structured delta",
            property_delta=None,
            substrate="casein",
        )
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "mutation-empty-delta-refresh@example.com",
            "password": "search-password",
            "display_name": "Mutation Empty Delta Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "mutation-empty-delta-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["mutations"] == 0
    mutations = db_session.scalars(select(MutationRecord).where(MutationRecord.enzyme_entry_id == enzyme.id)).all()
    assert len(mutations) == 1


def test_real_data_refresh_normalizes_external_doi_before_reference_lookup(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="52",
                    unit_original="degC",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC DOI URL optimum temperature",
                    reference_title="Shared DOI enzyme data",
                    journal="Enzyme and Microbial Technology",
                    year=2024,
                    doi="https://doi.org/10.1000/shared-doi-reference",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    existing_reference = LiteratureReference(
        title="Existing shared DOI enzyme data",
        journal="Enzyme and Microbial Technology",
        year=2024,
        doi="10.1000/shared-doi-reference",
        source="crossref",
    )
    db_session.add_all([enzyme, existing_reference])
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "doi-normalization-refresh@example.com",
            "password": "search-password",
            "display_name": "DOI Normalization Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "doi-normalization-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["references"] == 0
    references = db_session.scalars(select(LiteratureReference)).all()
    properties = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    assert len(references) == 1
    assert references[0].doi == "10.1000/shared-doi-reference"
    assert len(properties) == 1
    assert properties[0].reference_id == existing_reference.id


def test_real_data_refresh_reuses_legacy_url_doi_reference(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="53",
                    unit_original="degC",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC normalized DOI optimum temperature",
                    reference_title="Legacy DOI enzyme data",
                    journal="Enzyme and Microbial Technology",
                    year=2024,
                    doi="10.1000/legacy-url-doi-reference",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    existing_reference = LiteratureReference(
        title="Existing legacy DOI enzyme data",
        journal="Enzyme and Microbial Technology",
        year=2024,
        doi="https://doi.org/10.1000/legacy-url-doi-reference",
        source="crossref",
    )
    db_session.add_all([enzyme, existing_reference])
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "legacy-doi-refresh@example.com",
            "password": "search-password",
            "display_name": "Legacy DOI Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "legacy-doi-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["references"] == 0
    references = db_session.scalars(select(LiteratureReference)).all()
    properties = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    assert len(references) == 1
    assert properties[0].reference_id == existing_reference.id


def test_real_data_refresh_normalizes_external_pubmed_id_before_reference_lookup(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "pubmed"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="54",
                    unit_original="degC",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="PubMed prefixed PMID optimum temperature",
                    reference_title="Shared PubMed enzyme data",
                    journal="Enzyme and Microbial Technology",
                    year=2024,
                    pubmed_id="PMID: 10000004",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    existing_reference = LiteratureReference(
        title="Existing shared PubMed enzyme data",
        journal="Enzyme and Microbial Technology",
        year=2024,
        pubmed_id="10000004",
        source="pubmed",
    )
    db_session.add_all([enzyme, existing_reference])
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "pubmed-normalization-refresh@example.com",
            "password": "search-password",
            "display_name": "PubMed Normalization Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "pubmed-normalization-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["references"] == 0
    references = db_session.scalars(select(LiteratureReference)).all()
    properties = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    assert len(references) == 1
    assert references[0].pubmed_id == "10000004"
    assert properties[0].reference_id == existing_reference.id


def test_real_data_refresh_reuses_legacy_uppercase_pubmed_reference(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "pubmed"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="54",
                    unit_original="degC",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="PubMed uppercase PMID optimum temperature",
                    reference_title="Shared uppercase PubMed enzyme data",
                    journal="Enzyme and Microbial Technology",
                    year=2024,
                    pubmed_id="10000008",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    existing_reference = LiteratureReference(
        title="Existing shared uppercase PubMed enzyme data",
        journal="Enzyme and Microbial Technology",
        year=2024,
        pubmed_id="PUBMED: 10000008",
        source="pubmed",
    )
    db_session.add_all([enzyme, existing_reference])
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "pubmed-uppercase-refresh@example.com",
            "password": "search-password",
            "display_name": "PubMed Uppercase Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "pubmed-uppercase-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["references"] == 0
    references = db_session.scalars(select(LiteratureReference)).all()
    properties = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    assert len(references) == 1
    assert references[0].pubmed_id == "10000008"
    assert properties[0].reference_id == existing_reference.id


def test_real_data_refresh_normalizes_external_doi_case_before_reference_lookup(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="55",
                    unit_original="degC",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC mixed-case DOI optimum temperature",
                    reference_title="Mixed-case DOI enzyme data",
                    journal="Enzyme and Microbial Technology",
                    year=2024,
                    doi="10.1000/Mixed-Case-Reference",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    existing_reference = LiteratureReference(
        title="Existing mixed-case DOI enzyme data",
        journal="Enzyme and Microbial Technology",
        year=2024,
        doi="10.1000/mixed-case-reference",
        source="crossref",
    )
    db_session.add_all([enzyme, existing_reference])
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "doi-case-refresh@example.com",
            "password": "search-password",
            "display_name": "DOI Case Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "doi-case-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["references"] == 0
    references = db_session.scalars(select(LiteratureReference)).all()
    properties = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    assert len(references) == 1
    assert references[0].doi == "10.1000/mixed-case-reference"
    assert properties[0].reference_id == existing_reference.id


def test_real_data_refresh_reuses_legacy_mixed_case_doi_reference(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original="56",
                    unit_original="degC",
                    organism="Streptomyces mobaraensis",
                    source=self.source,
                    evidence="Europe PMC normalized DOI against legacy mixed case",
                    reference_title="Legacy mixed-case DOI enzyme data",
                    journal="Enzyme and Microbial Technology",
                    year=2024,
                    doi="10.1000/legacy-mixed-case-reference",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    existing_reference = LiteratureReference(
        title="Existing legacy mixed-case DOI enzyme data",
        journal="Enzyme and Microbial Technology",
        year=2024,
        doi="10.1000/Legacy-Mixed-Case-Reference",
        source="crossref",
    )
    db_session.add_all([enzyme, existing_reference])
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "legacy-doi-case-refresh@example.com",
            "password": "search-password",
            "display_name": "Legacy DOI Case Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "legacy-doi-case-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["created"]["references"] == 0
    references = db_session.scalars(select(LiteratureReference)).all()
    properties = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    assert len(references) == 1
    assert references[0].doi == "10.1000/legacy-mixed-case-reference"
    assert properties[0].reference_id == existing_reference.id


def test_real_data_refresh_saves_alphafold_structure_for_known_uniprot(client, db_session, monkeypatch):
    class EmptyEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    class RealAlphaFoldClient:
        source = "alphafold"

        def fetch_model_by_uniprot(self, uniprot_id: str):
            assert uniprot_id == "P12345"
            return AlphaFoldModelMetadata(
                model_id="AF-P12345-F1",
                uniprot_id="P12345",
                structure_url="https://alphafold.ebi.ac.uk/files/AF-P12345-F1-model_v6.pdb",
                confidence_url="https://alphafold.ebi.ac.uk/files/AF-P12345-F1-confidence_v6.json",
                confidence_summary={"avg_plddt": 88.0},
            )

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_alphafold_client", lambda: RealAlphaFoldClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Food hydrolases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Food hydrolase with AlphaFold",
        organism="Bacillus subtilis",
        source="uniprot",
        uniprot_id="P12345",
        alphafold_id="AF-P12345-F1",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "alphafold-real-refresh@example.com",
            "password": "search-password",
            "display_name": "AlphaFold Real Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "alphafold-real-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"]["structures"] == 1
    assert "alphafold" in body["sources"]
    structure = db_session.scalar(select(StructureEntry).where(StructureEntry.enzyme_entry_id == enzyme.id))
    assert structure.structure_type == "alphafold"
    assert structure.source == "alphafold"
    assert structure.chain_summary["model_id"] == "AF-P12345-F1"


def test_real_data_refresh_saves_rcsb_structure_for_known_pdb_id(client, db_session, monkeypatch):
    class EmptyEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    class RealRcsbClient:
        source = "rcsb"

        def fetch_structure_metadata(self, pdb_id: str):
            assert pdb_id == "1ABC"
            return RcsbStructureMetadata(
                pdb_id="1ABC",
                title="Real PDB-linked food enzyme",
                method="X-RAY DIFFRACTION",
                resolution=1.8,
                uniprot_id="P12346",
                organism="Bacillus subtilis",
                chain_summary={"polymer_entity_count": 1, "chains": ["A"]},
                ligand_summary={"ligands": ["CA"]},
            )

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_rcsb_client", lambda: RealRcsbClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Food oxidoreductases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Food oxidoreductase with PDB",
        organism="Bacillus subtilis",
        source="uniprot",
        uniprot_id="P12346",
        pdb_id="1ABC",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "rcsb-real-refresh@example.com",
            "password": "search-password",
            "display_name": "RCSB Real Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "rcsb-real-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"]["structures"] == 1
    assert "rcsb" in body["sources"]
    structure = db_session.scalar(select(StructureEntry).where(StructureEntry.enzyme_entry_id == enzyme.id))
    assert structure.structure_type == "pdb"
    assert structure.pdb_id == "1ABC"
    assert structure.source == "rcsb"
    assert structure.chain_summary["provenance"]["provider"] == "rcsb"


def test_real_data_refresh_updates_existing_rcsb_structure_state(client, db_session, monkeypatch):
    class EmptyEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    class RealRcsbClient:
        source = "rcsb"

        def fetch_structure_metadata(self, pdb_id: str):
            assert pdb_id == "1ABC"
            return RcsbStructureMetadata(
                pdb_id="1ABC",
                title="Real PDB-linked food enzyme",
                method="X-RAY DIFFRACTION",
                resolution=1.8,
                uniprot_id="P12346",
                organism="Bacillus subtilis",
                chain_summary={"polymer_entity_count": 1, "chains": ["A"]},
                ligand_summary={"ligands": []},
            )

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_rcsb_client", lambda: RealRcsbClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Food oxidoreductases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Food oxidoreductase with PDB",
        organism="Bacillus subtilis",
        source="uniprot",
        uniprot_id="P12346",
        pdb_id="1ABC",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    structure = StructureEntry(
        enzyme_entry_id=enzyme.id,
        structure_type="pdb",
        complex_state="unknown",
        pdb_id="1ABC",
        chain_summary={},
        ligand_summary={},
        source="rcsb",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(structure)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "rcsb-existing-refresh@example.com",
            "password": "search-password",
            "display_name": "RCSB Existing Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "rcsb-existing-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    db_session.refresh(structure)
    assert structure.complex_state == "apo"
    assert structure.chain_summary["chains"] == ["A"]
    assert structure.chain_summary["provenance"]["provider"] == "rcsb"
    assert structure.ligand_summary == {"ligands": []}


def test_family_real_data_refresh_updates_same_family_entries(client, db_session, monkeypatch):
    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original=f"{query} 62",
                    unit_original="degC",
                    organism=_organism_from_query(query),
                    source=self.source,
                    evidence=f"Europe PMC family property for {query}",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    def _organism_from_query(query: str):
        if "Geobacillus stearothermophilus" in query:
            return "Geobacillus stearothermophilus"
        return "Bacillus subtilis"

    class RealLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return [
                LiteratureMetadata(
                    title=f"Real family evidence for {enzyme_name}",
                    journal="Food Enzyme Reports",
                    year=2026,
                    doi=f"10.1000/{enzyme_name.lower().replace(' ', '-')}",
                    source=self.source,
                )
            ]

    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: RealDataClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: RealLiteratureClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Food lipases",
    )
    db_session.add(family)
    db_session.flush()
    first = EnzymeEntry(
        family_id=family.id,
        name="Food lipase Bacillus",
        organism="Bacillus subtilis",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    second = EnzymeEntry(
        family_id=family.id,
        name="Food lipase Geobacillus",
        organism="Geobacillus stearothermophilus",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add_all([first, second])
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "family-real-refresh@example.com",
            "password": "search-password",
            "display_name": "Family Real Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "family-real-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{first.id}/family-real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] == {"references": 2, "properties": 2, "kinetics": 0, "mutations": 0, "structures": 0}
    assert body["sources"] == ["crossref", "europepmc"]

    refreshed = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id.in_([first.id, second.id]))).all()
    assert {record.enzyme_entry_id for record in refreshed} == {first.id, second.id}


def test_real_data_refresh_rejects_mock_provider(client, db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Mock-only microbial transglutaminase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "mock-refresh@example.com",
            "password": "search-password",
            "display_name": "Mock Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "mock-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert db_session.scalar(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)) is None


def test_real_data_refresh_job_endpoint_enqueues_without_fetching_inline(client, db_session, monkeypatch):
    enqueued_job_ids = []

    class RealDataRefreshTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    def fail_if_called():
        raise AssertionError("real data refresh should run in the worker, not in the request")

    monkeypatch.setattr("app.api.routes.enzymes.run_real_data_refresh", RealDataRefreshTask, raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", fail_if_called)

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Async real data mTGase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "async-real-data@example.com",
            "password": "search-password",
            "display_name": "Async Real Data",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "async-real-data@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/real-data/refresh-job",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_type"] == "real_data_refresh"
    assert body["status"] == "queued"
    assert body["enzyme_entry_id"] == enzyme.id
    assert body["parameters_json"] == {"scope": "enzyme"}
    assert enqueued_job_ids == [body["id"]]


def test_family_real_data_refresh_job_endpoint_enqueues_family_scope(client, db_session, monkeypatch):
    enqueued_job_ids = []

    class RealDataRefreshTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr("app.api.routes.enzymes.run_real_data_refresh", RealDataRefreshTask, raising=False)

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Async family real data mTGase",
        organism="Streptomyces mobaraensis",
        source="uniprot",
        uniprot_id="P81453",
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "async-family-real-data@example.com",
            "password": "search-password",
            "display_name": "Async Family Real Data",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "async-family-real-data@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        f"/enzymes/{enzyme.id}/family-real-data/refresh-job",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_type"] == "real_data_refresh"
    assert body["parameters_json"] == {"scope": "family"}
    assert enqueued_job_ids == [body["id"]]


def test_enzyme_search_reuses_fresh_search_cache(client, db_session, monkeypatch):
    enqueued_job_ids = []

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "cache-searcher@example.com",
            "password": "search-password",
            "display_name": "Cache Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "cache-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    first_response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P12345"},
    )
    second_response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P12345"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["cache_status"] == "miss_refreshed"
    assert second_response.json()["cache_status"] == "hit"
    assert second_response.json()["enzyme"]["id"] == first_response.json()["enzyme"]["id"]

    cache_records = list(
        db_session.scalars(
            select(SearchCacheRecord).where(SearchCacheRecord.normalized_query == "P12345")
        )
    )
    assert len(cache_records) == 1
    assert cache_records[0].payload_json["enzyme_entry_id"] == first_response.json()["enzyme"]["id"]
    assert enqueued_job_ids == [first_response.json()["job_id"], second_response.json()["job_id"]]


def test_enzyme_search_marks_stale_data_modules_for_partial_refresh(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "partial-refresh@example.com",
            "password": "search-password",
            "display_name": "Partial Refresh",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "partial-refresh@example.com", "password": "search-password"},
    ).json()["access_token"]

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Fresh local mTGase",
        organism="Streptomyces mobaraensis",
        uniprot_id="P55555",
        source="local",
        last_refreshed_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNG",
            mature_sequence="AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNG",
            source="test",
            checksum="partial-refresh-sequence",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
    )
    db_session.commit()

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P55555"},
    )

    assert response.status_code == 200
    job = db_session.get(AnalysisJob, response.json()["job_id"])
    assert job is not None
    refresh_modules = job.parameters_json["refresh_modules"]
    assert DATA_MODULE_SEQUENCE not in refresh_modules
    assert DATA_MODULE_STRUCTURE in refresh_modules


def test_enzyme_search_refreshes_stale_search_cache(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "stale-cache-searcher@example.com",
            "password": "search-password",
            "display_name": "Stale Cache Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "stale-cache-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    first_response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P67890"},
    )
    assert first_response.status_code == 200

    cache_record = db_session.scalar(
        select(SearchCacheRecord).where(SearchCacheRecord.normalized_query == "P67890")
    )
    assert cache_record is not None
    cache_record.last_refreshed_at = datetime.utcnow() - timedelta(days=16)
    db_session.commit()

    second_response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P67890"},
    )

    assert second_response.status_code == 200
    assert second_response.json()["cache_status"] == "stale_refreshed"
    db_session.refresh(cache_record)
    assert cache_record.last_refreshed_at > datetime.utcnow() - timedelta(days=1)


def test_enzyme_search_hits_local_entry_by_pdb_id(client, db_session, monkeypatch):
    enqueued_job_ids = []

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="PDB-backed mTGase",
        organism="Streptomyces mobaraensis",
        pdb_id="1ABC",
        source="local",
        last_refreshed_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "pdb-searcher@example.com",
            "password": "search-password",
            "display_name": "PDB Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "pdb-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "1abc"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_status"] == "hit"
    assert body["query_kind"] == "pdb"
    assert body["enzyme"]["id"] == enzyme.id
    assert body["enzyme"]["pdb_id"] == "1ABC"
    assert enqueued_job_ids == [body["job_id"]]


def test_enzyme_search_hits_local_entry_by_alphafold_id(client, db_session, monkeypatch):
    enqueued_job_ids = []

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="AlphaFold-backed mTGase",
        organism="Streptomyces mobaraensis",
        uniprot_id="P81453",
        alphafold_id="AF-P81453-F1",
        source="local",
        last_refreshed_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "alphafold-searcher@example.com",
            "password": "search-password",
            "display_name": "AlphaFold Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "alphafold-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "af-p81453-f1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_status"] == "hit"
    assert body["query_kind"] == "alphafold"
    assert body["enzyme"]["id"] == enzyme.id
    assert body["enzyme"]["alphafold_id"] == "AF-P81453-F1"
    assert enqueued_job_ids == [body["job_id"]]


def test_enzyme_search_enqueues_real_homology_collection_job(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Real job mTGase",
        organism="Streptomyces mobaraensis",
        uniprot_id="P81453",
        source="local",
        last_refreshed_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence=P81453_FULL_SEQUENCE,
            mature_sequence=P81453_MATURE_SEQUENCE,
            source="local",
            checksum="real-job-sequence",
        )
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "homology-searcher@example.com",
            "password": "search-password",
            "display_name": "Homology Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "homology-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P81453"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"]

    job = db_session.scalar(select(AnalysisJob).where(AnalysisJob.id == body["job_id"]))
    assert job is not None
    assert job.job_type == "homolog_collection"


def test_enzyme_search_fetches_uniprot_entry_from_alphafold_id_when_not_local(
    client,
    db_session,
    monkeypatch,
):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FakeUniProtClient:
        source = "uniprot_mock"

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_keyword(self, keyword: str, size: int = 5):
            return []

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            assert accession == "P81453"
            return UniProtEntry(
                accession=accession,
                protein_name="AlphaFold resolved enzyme",
                organism="Streptomyces mobaraensis",
                sequence="MNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
                cross_references={"AlphaFoldDB": "AF-P81453-F1"},
            )

        def fetch_fasta(self, accession: str):
            return ">sp|P81453|MOCK\nMNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN\n"

        def fetch_cross_references(self, accession: str):
            return {"AlphaFoldDB": "AF-P81453-F1"}

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: FakeUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "alphafold-uniprot-searcher@example.com",
            "password": "search-password",
            "display_name": "AlphaFold UniProt Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "alphafold-uniprot-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "AF-P81453-F1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_status"] == "miss_refreshed"
    assert body["query_kind"] == "alphafold"
    assert body["enzyme"]["uniprot_id"] == "P81453"
    assert body["enzyme"]["alphafold_id"] == "AF-P81453-F1"


def test_enzyme_search_refreshes_stale_local_pdb_match(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Stale PDB-backed mTGase",
        organism="Streptomyces mobaraensis",
        pdb_id="2DEF",
        source="local",
        last_refreshed_at=datetime.utcnow() - timedelta(days=16),
    )
    db_session.add(enzyme)
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "stale-pdb-searcher@example.com",
            "password": "search-password",
            "display_name": "Stale PDB Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "stale-pdb-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "2def"},
    )

    assert response.status_code == 200
    assert response.json()["cache_status"] == "stale_refreshed"
    assert response.json()["enzyme"]["id"] == enzyme.id
    db_session.refresh(enzyme)
    assert enzyme.last_refreshed_at > datetime.utcnow() - timedelta(days=1)


def test_enzyme_search_fetches_rcsb_metadata_when_pdb_not_local(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "rcsb-pdb-searcher@example.com",
            "password": "search-password",
            "display_name": "RCSB PDB Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "rcsb-pdb-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "1abc"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_status"] == "miss_refreshed"
    assert body["query_kind"] == "pdb"
    assert body["enzyme"]["pdb_id"] == "1ABC"
    assert body["enzyme"]["uniprot_id"] == "MOCKMTG1"

    structure = db_session.scalar(
        select(StructureEntry).where(StructureEntry.enzyme_entry_id == body["enzyme"]["id"])
    )
    assert structure is not None
    assert structure.pdb_id == "1ABC"
    assert structure.source == "rcsb_mock"
    assert structure.chain_summary["polymer_entity_count"] == 1
    assert structure.chain_summary["chains"] == ["A"]
    assert structure.chain_summary["provenance"]["provider"] == "rcsb_mock"
    assert structure.chain_summary["provenance"]["mode"] == "fallback"
    assert structure.chain_summary["provenance"]["source_url"] == "https://www.rcsb.org/structure/1ABC"
    assert structure.ligand_summary == {"ligands": ["GTP"]}


def test_enzyme_search_reports_rcsb_provider_failure_without_mock_fallback(
    client,
    db_session,
    monkeypatch,
):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FailingRcsbClient:
        source = "rcsb"

        def fetch_structure_metadata(self, pdb_id: str):
            raise httpx.ConnectError("rcsb offline")

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_rcsb_client",
        lambda: FailingRcsbClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "rcsb-failure@example.com",
            "password": "search-password",
            "display_name": "RCSB Failure Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "rcsb-failure@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "1abc"},
    )

    assert response.status_code == 503
    assert "RCSB provider unavailable" in response.json()["error"]["message"]
    assert db_session.scalar(select(StructureEntry).where(StructureEntry.source == "rcsb_mock")) is None


def test_enzyme_search_hits_level_two_sequence_similarity(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    sequence = "AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNGDKVTVEQSNNG"
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Similar sequence mTGase",
        organism="Streptomyces mobaraensis",
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
            checksum="similar-sequence-checksum",
        )
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "sequence-searcher@example.com",
            "password": "search-password",
            "display_name": "Sequence Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "sequence-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": sequence},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_status"] == "hit"
    assert body["query_kind"] == "sequence"
    assert body["enzyme"]["id"] == enzyme.id


def test_enzyme_search_uses_uniprot_connector_for_ec_refresh(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FakeUniProtClient:
        source = "uniprot_mock"

        def search_by_ec(self, ec_number: str, size: int = 5):
            assert ec_number == "2.3.2.13"
            return [
                UniProtSearchHit(
                    accession="U11111",
                    protein_name="Connector microbial transglutaminase",
                    organism="Streptomyces testingensis",
                    ec_number=ec_number,
                    sequence="MSTNPKPQRKTKRNTNRRPQDVKFPGGGQIVGGVY",
                    cross_references={"AlphaFoldDB": "AF-U11111-F1"},
                )
            ]

        def search_by_keyword(self, keyword: str, size: int = 5):
            raise AssertionError("EC search should not call keyword search")

        def search_by_organism(self, organism: str, size: int = 5):
            raise AssertionError("EC search should not call organism search")

        def fetch_entry(self, accession: str):
            assert accession == "U11111"
            return UniProtEntry(
                accession=accession,
                protein_name="Connector microbial transglutaminase",
                organism="Streptomyces testingensis",
                ec_number="2.3.2.13",
                sequence="MSTNPKPQRKTKRNTNRRPQDVKFPGGGQIVGGVY",
                cross_references={"AlphaFoldDB": "AF-U11111-F1"},
            )

        def fetch_fasta(self, accession: str):
            return ">sp|U11111|MOCK\nMSTNPKPQRKTKRNTNRRPQDVKFPGGGQIVGGVY\n"

        def fetch_cross_references(self, accession: str):
            return {"AlphaFoldDB": "AF-U11111-F1"}

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: FakeUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "ec-connector@example.com",
            "password": "search-password",
            "display_name": "EC Connector Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "ec-connector@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "2.3.2.13"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_status"] == "miss_refreshed"
    assert body["query_kind"] == "ec"
    assert body["enzyme"]["uniprot_id"] == "U11111"
    assert body["enzyme"]["name"] == "Connector microbial transglutaminase"

    enzyme = db_session.get(EnzymeEntry, body["enzyme"]["id"])
    assert enzyme is not None
    assert enzyme.source == "uniprot_mock"
    sequence = db_session.scalar(select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == enzyme.id))
    assert sequence is not None
    assert sequence.sequence == "MSTNPKPQRKTKRNTNRRPQDVKFPGGGQIVGGVY"


def test_real_keyword_search_persists_multiple_uniprot_hits(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class UnexpectedLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            raise AssertionError("real search should not synchronously fetch literature")

    class UnexpectedEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            raise AssertionError("real search should not synchronously fetch enzyme data")

        def fetch_opt_pH(self, query: str, size: int = 5):
            raise AssertionError("real search should not synchronously fetch enzyme data")

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            raise AssertionError("real search should not synchronously fetch enzyme data")

        def fetch_mutants(self, query: str, size: int = 5):
            raise AssertionError("real search should not synchronously fetch enzyme data")

    class FakeUniProtClient:
        source = "uniprot"
        fetch_entry_calls: list[str] = []
        search_calls: int = 0

        def search_by_ec(self, ec_number: str, size: int = 5):
            raise AssertionError("keyword search should not call EC search")

        def search_by_keyword(self, keyword: str, size: int = 5):
            self.__class__.search_calls += 1
            assert keyword == "food lipase"
            assert size == 3
            return [
                UniProtSearchHit(
                    accession="R11111",
                    protein_name="Food lipase alpha",
                    organism="Bacillus realensis",
                    ec_number="3.1.1.3",
                    score=90.0,
                ),
                UniProtSearchHit(
                    accession="R22222",
                    protein_name="Food lipase beta",
                    organism="Geobacillus realensis",
                    ec_number="3.1.1.3",
                    score=80.0,
                ),
                UniProtSearchHit(
                    accession="R33333",
                    protein_name="Food lipase gamma",
                    organism="Aspergillus realensis",
                    ec_number="3.1.1.3",
                    score=70.0,
                ),
            ]

        def search_by_organism(self, organism: str, size: int = 5):
            raise AssertionError("keyword search should not call organism search")

        def fetch_entry(self, accession: str):
            return UniProtEntry(
                accession=accession,
                protein_name={
                    "R11111": "Food lipase alpha",
                    "R22222": "Food lipase beta",
                    "R33333": "Food lipase gamma",
                }[accession],
                organism={
                    "R11111": "Bacillus realensis",
                    "R22222": "Geobacillus realensis",
                    "R33333": "Aspergillus realensis",
                }[accession],
                ec_number="3.1.1.3",
                    sequence=f"M{accession}SEQUENCE",
                    mature_sequence=f"MATURE{accession}",
                    reviewed=True,
                    cross_references={"AlphaFoldDB": f"AF-{accession}-F1"},
                )

        def fetch_fasta(self, accession: str):
            return f">sp|{accession}|REAL\nM{accession}SEQUENCE\n"

    class EmptyAlphaFoldClient:
        source = "alphafold"

        def fetch_model_by_uniprot(self, uniprot_id: str):
            raise ValueError("no AlphaFold model in this test")

    monkeypatch.setattr("app.api.routes.enzymes.run_homology_collection", PlaceholderTask, raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_uniprot_client", lambda: FakeUniProtClient(), raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_alphafold_client", lambda: EmptyAlphaFoldClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: UnexpectedLiteratureClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: UnexpectedEnzymeDataClient())

    client.post(
        "/auth/register",
        json={
            "email": "multi-real-search@example.com",
            "password": "search-password",
            "display_name": "Multi Real Search",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "multi-real-search@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "food lipase", "result_limit": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert {match["uniprot_id"] for match in body["matches"]} == {"R11111", "R22222", "R33333"}
    assert {match["source"] for match in body["matches"]} == {"uniprot"}
    assert FakeUniProtClient.search_calls == 1
    assert body["enzyme"]["uniprot_id"] == "R11111"
    assert (
        db_session.scalar(select(EnzymeEntry).where(EnzymeEntry.uniprot_id == "R33333"))
        is not None
    )


def test_keyword_search_backfills_real_uniprot_sources_when_local_results_are_sparse(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    class EmptyEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyAlphaFoldClient:
        source = "alphafold"

        def fetch_model_by_uniprot(self, uniprot_id: str):
            raise ValueError("no AlphaFold model in this test")

    class FakeUniProtClient:
        source = "uniprot"

        def search_by_ec(self, ec_number: str, size: int = 5):
            raise AssertionError("keyword search should not call EC search")

        def search_by_keyword(self, keyword: str, size: int = 5):
            assert keyword == "microbial transglutaminase"
            assert size == 4
            return [
                UniProtSearchHit(
                    accession="P81453",
                    protein_name="Protein-glutamine gamma-glutamyltransferase",
                    organism="Streptomyces mobaraensis",
                    ec_number="2.3.2.13",
                    score=90.0,
                    sequence="MP81453SEQUENCE",
                    mature_sequence="MATUREP81453",
                    reviewed=True,
                    cross_references={"AlphaFoldDB": "AF-P81453-F1", "PDB": "1IU4"},
                ),
                UniProtSearchHit(
                    accession="Q11111",
                    protein_name="Protein-glutamine gamma-glutamyltransferase",
                    organism="Streptomyces hygroscopicus",
                    ec_number="2.3.2.13",
                    score=80.0,
                    sequence="MQ11111SEQUENCE",
                    mature_sequence="MATUREQ11111",
                    cross_references={"AlphaFoldDB": "AF-Q11111-F1", "PDB": "1TG"},
                ),
                UniProtSearchHit(
                    accession="Q22222",
                    protein_name="Protein-glutamine gamma-glutamyltransferase",
                    organism="Streptomyces cinnamoneus",
                    ec_number="2.3.2.13",
                    score=70.0,
                    sequence="MQ22222SEQUENCE",
                    mature_sequence="MATUREQ22222",
                    cross_references={"AlphaFoldDB": "AF-Q22222-F1", "PDB": "2TG"},
                ),
                UniProtSearchHit(
                    accession="Q33333",
                    protein_name="Protein-glutamine gamma-glutamyltransferase",
                    organism="Streptomyces netropsis",
                    ec_number="2.3.2.13",
                    score=60.0,
                    sequence="MQ33333SEQUENCE",
                    mature_sequence="MATUREQ33333",
                    cross_references={"AlphaFoldDB": "AF-Q33333-F1", "PDB": "3TG"},
                ),
            ]

        def search_by_organism(self, organism: str, size: int = 5):
            raise AssertionError("keyword search should not call organism search")

        def fetch_entry(self, accession: str):
            self.__class__.fetch_entry_calls.append(accession)
            organisms = {
                "P81453": "Streptomyces mobaraensis",
                "Q11111": "Streptomyces hygroscopicus",
                "Q22222": "Streptomyces cinnamoneus",
                "Q33333": "Streptomyces netropsis",
            }
            return UniProtEntry(
                accession=accession,
                protein_name="Protein-glutamine gamma-glutamyltransferase",
                organism=organisms[accession],
                ec_number="2.3.2.13",
                sequence=f"M{accession}SEQUENCE",
                mature_sequence=f"MATURE{accession}",
                reviewed=accession == "P81453",
                cross_references={
                    "AlphaFoldDB": f"AF-{accession}-F1",
                    "PDB": "1IU4" if accession == "P81453" else f"{accession[-1]}TG",
                },
            )

        def fetch_fasta(self, accession: str):
            raise AssertionError("keyword search should use sequence from UniProt entry instead of fetching FASTA")

    class FakeRcsbClient:
        source = "rcsb"

        def fetch_structure_metadata(self, pdb_id: str):
            raise AssertionError("keyword search should defer RCSB metadata fetch until structure/detail refresh")

        def search_by_uniprot(self, uniprot_id: str, size: int = 5):
            return []

        def search_by_keyword(self, keyword: str, size: int = 5):
            return []

    FakeUniProtClient.fetch_entry_calls = []

    monkeypatch.setattr("app.api.routes.enzymes.run_homology_collection", PlaceholderTask, raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_uniprot_client", lambda: FakeUniProtClient(), raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_alphafold_client", lambda: EmptyAlphaFoldClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_rcsb_client", lambda: FakeRcsbClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())

    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Protein-glutamine gamma-glutamyltransferases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Protein-glutamine gamma-glutamyltransferase",
        organism="Streptomyces mobaraensis",
        ec_number="2.3.2.13",
        uniprot_id="P81453",
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    for accession, organism in [
        ("Q11111", "Streptomyces hygroscopicus"),
        ("Q22222", "Streptomyces cinnamoneus"),
        ("Q33333", "Streptomyces netropsis"),
    ]:
        db_session.add(
            EnzymeEntry(
                family_id=family.id,
                name="Protein-glutamine gamma-glutamyltransferase",
                organism=organism,
                ec_number="2.3.2.13",
                uniprot_id=accession,
                source="uniprot",
                last_refreshed_at=datetime.utcnow(),
            )
        )
    job = AnalysisJob(
        enzyme_entry_id=enzyme.id,
        job_type="homolog_collection",
        status=JobStatus.FINISHED,
    )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        SearchCacheRecord(
            query="microbial transglutaminase",
            normalized_query="microbial transglutaminase",
            query_kind="keyword",
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            enzyme_entry_id=enzyme.id,
            payload_json={"job_id": job.id, "enzyme_entry_id": enzyme.id},
            source="uniprot",
            last_refreshed_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    client.post(
        "/auth/register",
        json={
            "email": "cached-tgase-searcher@example.com",
            "password": "search-password",
            "display_name": "Cached TGase Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "cached-tgase-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "microbial transglutaminase", "result_limit": 4},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_status"] == "miss_refreshed"
    assert {match["uniprot_id"] for match in body["matches"]} == {
        "P81453",
        "Q11111",
        "Q22222",
        "Q33333",
    }
    assert FakeUniProtClient.fetch_entry_calls == []
    assert body["enzyme"]["pdb_id"] == "1IU4"
    assert db_session.scalars(select(StructureEntry).where(StructureEntry.source == "rcsb")).all() == []
    assert {match["organism"] for match in body["matches"]} == {
        "Streptomyces mobaraensis",
        "Streptomyces hygroscopicus",
        "Streptomyces cinnamoneus",
        "Streptomyces netropsis",
    }


def test_keyword_search_keeps_sparse_uniprot_hits_when_entry_details_fail(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    class EmptyEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class FlakyUniProtClient:
        source = "uniprot"

        def search_by_ec(self, ec_number: str, size: int = 5):
            raise AssertionError("keyword search should not call EC search")

        def search_by_keyword(self, keyword: str, size: int = 5):
            return [
                UniProtSearchHit(
                    accession="P81453",
                    protein_name="Protein-glutamine gamma-glutamyltransferase",
                    organism="Streptomyces mobaraensis",
                    ec_number="2.3.2.13",
                    score=90.0,
                )
            ]

        def search_by_organism(self, organism: str, size: int = 5):
            raise AssertionError("keyword search should not call organism search")

        def fetch_entry(self, accession: str):
            raise httpx.ConnectError("UniProt entry endpoint unavailable")

        def fetch_fasta(self, accession: str):
            raise AssertionError("FASTA should not be fetched when details fail")

    monkeypatch.setattr("app.api.routes.enzymes.run_homology_collection", PlaceholderTask, raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_uniprot_client", lambda: FlakyUniProtClient(), raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())

    client.post(
        "/auth/register",
        json={
            "email": "flaky-uniprot-searcher@example.com",
            "password": "search-password",
            "display_name": "Flaky UniProt Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "flaky-uniprot-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "microbial transglutaminase", "result_limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enzyme"]["uniprot_id"] == "P81453"
    assert body["enzyme"]["pdb_id"] is None
    assert body["matches"][0]["organism"] == "Streptomyces mobaraensis"


def test_keyword_search_expands_uniprot_query_when_primary_keyword_has_no_hits(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    class EmptyEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyAlphaFoldClient:
        source = "alphafold"

        def fetch_model_by_uniprot(self, uniprot_id: str):
            raise ValueError("no AlphaFold model in this test")

    class ExpandingUniProtClient:
        source = "uniprot"
        queries: list[str] = []

        def search_by_ec(self, ec_number: str, size: int = 5):
            raise AssertionError("keyword search should not call EC search")

        def search_by_keyword(self, keyword: str, size: int = 5):
            self.queries.append(keyword)
            if keyword == "cellobiose 2-epimerase":
                return []
            if keyword == 'protein_name:"cellobiose 2-epimerase"':
                return [
                    UniProtSearchHit(
                        accession="Q9X123",
                        protein_name="Cellobiose 2-epimerase",
                        organism="Dictyoglomus turgidum",
                        ec_number="5.1.3.11",
                        sequence="MCESEQUENCE",
                        mature_sequence="CESEQUENCE",
                        reviewed=True,
                        cross_references={"AlphaFoldDB": "AF-Q9X123-F1"},
                    )
                ]
            return []

        def search_by_organism(self, organism: str, size: int = 5):
            raise AssertionError("keyword search should use keyword variants")

        def fetch_entry(self, accession: str):
            raise AssertionError("keyword search should use sparse hit details")

        def fetch_fasta(self, accession: str):
            raise AssertionError("FASTA should not be fetched for sparse hit details")

    uniprot_client = ExpandingUniProtClient()
    monkeypatch.setattr("app.api.routes.enzymes.run_homology_collection", PlaceholderTask, raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_uniprot_client", lambda: uniprot_client, raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_alphafold_client", lambda: EmptyAlphaFoldClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())

    client.post(
        "/auth/register",
        json={
            "email": "expanded-uniprot-searcher@example.com",
            "password": "search-password",
            "display_name": "Expanded UniProt Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "expanded-uniprot-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "cellobiose 2-epimerase", "result_limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enzyme"]["uniprot_id"] == "Q9X123"
    assert body["enzyme"]["organism"] == "Dictyoglomus turgidum"
    assert uniprot_client.queries == [
        "cellobiose 2-epimerase",
        'protein_name:"cellobiose 2-epimerase"',
    ]


def test_keyword_search_passes_source_organism_to_uniprot(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    class EmptyEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyAlphaFoldClient:
        source = "alphafold"

        def fetch_model_by_uniprot(self, uniprot_id: str):
            raise ValueError("no AlphaFold model in this test")

    class FakeUniProtClient:
        source = "uniprot"

        def search_by_ec(self, ec_number: str, size: int = 5):
            raise AssertionError("organism-filtered keyword search should not call EC search")

        def search_by_keyword(self, keyword: str, size: int = 5):
            assert keyword == 'food lipase AND organism_name:"Bacillus realensis"'
            return [
                UniProtSearchHit(
                    accession="B11111",
                    protein_name="Bacillus food lipase",
                    organism="Bacillus realensis",
                    ec_number="3.1.1.3",
                )
            ]

        def search_by_organism(self, organism: str, size: int = 5):
            raise AssertionError("combined enzyme/source search should use a single UniProt query")

        def fetch_entry(self, accession: str):
            return UniProtEntry(
                accession=accession,
                protein_name="Bacillus food lipase",
                organism="Bacillus realensis",
                ec_number="3.1.1.3",
                sequence="MBACILLUSLIPASESEQUENCE",
                mature_sequence="BACILLUSLIPASESEQUENCE",
                cross_references={},
            )

        def fetch_fasta(self, accession: str):
            return ">sp|B11111|REAL\nMBACILLUSLIPASESEQUENCE\n"

    monkeypatch.setattr("app.api.routes.enzymes.run_homology_collection", PlaceholderTask, raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_uniprot_client", lambda: FakeUniProtClient(), raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_alphafold_client", lambda: EmptyAlphaFoldClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())

    client.post(
        "/auth/register",
        json={
            "email": "source-search@example.com",
            "password": "search-password",
            "display_name": "Source Search",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "source-search@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "query": "food lipase",
            "organism": "Bacillus realensis",
            "result_limit": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enzyme"]["organism"] == "Bacillus realensis"
    assert body["enzyme"]["family_name"] == "Bacillus food lipase"
    assert body["matches"][0]["uniprot_id"] == "B11111"


def test_real_uniprot_keyword_search_creates_family_from_enzyme_class(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class EmptyLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            return []

    class EmptyEnzymeDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return []

        def fetch_opt_pH(self, query: str, size: int = 5):
            return []

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return []

        def fetch_mutants(self, query: str, size: int = 5):
            return []

    class EmptyAlphaFoldClient:
        source = "alphafold"

        def fetch_model_by_uniprot(self, uniprot_id: str):
            raise ValueError("no AlphaFold model in this test")

    class FakeUniProtClient:
        source = "uniprot"

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_keyword(self, keyword: str, size: int = 5):
            return [
                UniProtSearchHit(
                    accession="LIP001",
                    protein_name="Triacylglycerol lipase",
                    organism="Bacillus subtilis",
                    ec_number="3.1.1.3",
                )
            ]

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            return UniProtEntry(
                accession=accession,
                protein_name="Triacylglycerol lipase",
                organism="Bacillus subtilis",
                ec_number="3.1.1.3",
                sequence="MLIPASESEQUENCE",
                mature_sequence=None,
                cross_references={},
            )

        def fetch_fasta(self, accession: str):
            return ">sp|LIP001|LIPA_BACSU\nMLIPASESEQUENCE\n"

    monkeypatch.setattr("app.api.routes.enzymes.run_homology_collection", PlaceholderTask, raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_uniprot_client", lambda: FakeUniProtClient(), raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_alphafold_client", lambda: EmptyAlphaFoldClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())

    client.post(
        "/auth/register",
        json={
            "email": "generic-family-search@example.com",
            "password": "search-password",
            "display_name": "Generic Family Search",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "generic-family-search@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "food lipase", "result_limit": 10},
    )

    assert response.status_code == 200
    enzyme_id = response.json()["enzyme"]["id"]
    enzyme = db_session.get(EnzymeEntry, enzyme_id)
    family = db_session.get(EnzymeFamily, enzyme.family_id)
    assert family.name == "Triacylglycerol lipase"
    assert family.name != "Mature microbial transglutaminases"


def test_enzyme_search_fetches_uniprot_accession_when_not_local(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FakeUniProtClient:
        source = "uniprot_mock"

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_keyword(self, keyword: str, size: int = 5):
            return []

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            assert accession == "P99999"
            return UniProtEntry(
                accession=accession,
                protein_name="Fetched UniProt enzyme",
                organism="Bacillus testingensis",
                ec_number=None,
                sequence="MNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
                cross_references={},
            )

        def fetch_fasta(self, accession: str):
            return ">sp|P99999|MOCK\nMNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN\n"

        def fetch_cross_references(self, accession: str):
            return {}

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: FakeUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "uniprot-connector@example.com",
            "password": "search-password",
            "display_name": "UniProt Connector Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "uniprot-connector@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P99999"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_status"] == "miss_refreshed"
    assert body["query_kind"] == "uniprot"
    assert body["enzyme"]["uniprot_id"] == "P99999"
    assert body["enzyme"]["name"] == "Fetched UniProt enzyme"


def test_enzyme_search_records_uniprot_retrieval_provenance(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FakeUniProtClient:
        source = "uniprot"

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_keyword(self, keyword: str, size: int = 5):
            return []

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            return UniProtEntry(
                accession=accession,
                protein_name="Traceable UniProt enzyme",
                organism="Bacillus provenance",
                sequence="MNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
                cross_references={
                    "provenance": {
                        "provider": "uniprot",
                        "mode": "real",
                        "retrieved_at": "2026-05-21T00:00:00Z",
                        "source_url": f"https://rest.uniprot.org/uniprotkb/{accession}.json",
                    }
                },
            )

        def fetch_fasta(self, accession: str):
            return ">sp|P77777|REAL\nMNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN\n"

        def fetch_cross_references(self, accession: str):
            return {}

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: FakeUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "uniprot-provenance@example.com",
            "password": "search-password",
            "display_name": "UniProt Provenance Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "uniprot-provenance@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P77777"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["retrieval_provenance"]["provider"] == "uniprot"
    assert body["retrieval_provenance"]["mode"] == "real"
    job = db_session.get(AnalysisJob, body["job_id"])
    assert job.parameters_json["retrieval_provenance"]["provider"] == "uniprot"
    assert job.parameters_json["retrieval_provenance"]["mode"] == "real"

    cache_record = db_session.scalar(
        select(SearchCacheRecord).where(SearchCacheRecord.normalized_query == "P77777")
    )
    assert cache_record.payload_json["retrieval_provenance"]["source_url"].endswith("/P77777.json")


def test_enzyme_search_reports_uniprot_provider_failure_without_mock_fallback(
    client,
    db_session,
    monkeypatch,
):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FailingUniProtClient:
        source = "uniprot"

        def search_by_ec(self, ec_number: str, size: int = 5):
            raise httpx.ConnectError("offline")

        def search_by_keyword(self, keyword: str, size: int = 5):
            raise httpx.ConnectError("offline")

        def search_by_organism(self, organism: str, size: int = 5):
            raise httpx.ConnectError("offline")

        def fetch_entry(self, accession: str):
            raise httpx.ConnectError("offline")

        def fetch_fasta(self, accession: str):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: FailingUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "uniprot-failure@example.com",
            "password": "search-password",
            "display_name": "UniProt Failure Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "uniprot-failure@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "microbial transglutaminase"},
    )

    assert response.status_code == 503
    assert "UniProt provider unavailable" in response.json()["error"]["message"]
    assert db_session.scalar(select(EnzymeEntry).where(EnzymeEntry.source == "uniprot_mock")) is None


def test_enzyme_search_saves_alphafold_structure_from_uniprot_cross_reference(
    client,
    db_session,
    monkeypatch,
):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FakeUniProtClient:
        source = "uniprot_mock"

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_keyword(self, keyword: str, size: int = 5):
            return []

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            assert accession == "P99998"
            return UniProtEntry(
                accession=accession,
                protein_name="AlphaFold linked enzyme",
                organism="Bacillus testingensis",
                ec_number=None,
                sequence="MNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
                cross_references={"AlphaFoldDB": "AF-P99998-F1"},
            )

        def fetch_fasta(self, accession: str):
            return ">sp|P99998|MOCK\nMNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN\n"

        def fetch_cross_references(self, accession: str):
            return {"AlphaFoldDB": "AF-P99998-F1"}

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: FakeUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "alphafold-connector@example.com",
            "password": "search-password",
            "display_name": "AlphaFold Connector Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "alphafold-connector@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P99998"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enzyme"]["alphafold_id"] == "AF-P99998-F1"

    structure = db_session.scalar(
        select(StructureEntry).where(StructureEntry.enzyme_entry_id == body["enzyme"]["id"])
    )
    assert structure is not None
    assert structure.structure_type == "alphafold"
    assert structure.complex_state == "predicted"
    assert structure.source == "alphafold_mock"
    assert structure.chain_summary["model_id"] == "AF-P99998-F1"
    assert structure.chain_summary["confidence_summary"]["mean_plddt"] == 90.0
    assert structure.chain_summary["provenance"]["provider"] == "alphafold_mock"
    assert structure.chain_summary["provenance"]["mode"] == "fallback"
    assert structure.chain_summary["provenance"]["source_url"] == "mock://alphafold/AF-P99998-F1.pdb"


def test_enzyme_search_saves_rcsb_structure_from_uniprot_cross_reference(
    client,
    db_session,
    monkeypatch,
):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FakeUniProtClient:
        source = "uniprot_mock"

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_keyword(self, keyword: str, size: int = 5):
            return []

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            assert accession == "P99996"
            return UniProtEntry(
                accession=accession,
                protein_name="RCSB linked enzyme",
                organism="Bacillus testingensis",
                ec_number=None,
                sequence="MNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
                cross_references={"PDB": "1ABC"},
            )

        def fetch_fasta(self, accession: str):
            return ">sp|P99996|MOCK\nMNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN\n"

        def fetch_cross_references(self, accession: str):
            return {"PDB": "1ABC"}

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: FakeUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "rcsb-connector@example.com",
            "password": "search-password",
            "display_name": "RCSB Connector Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "rcsb-connector@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P99996"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enzyme"]["pdb_id"] == "1ABC"

    structure = db_session.scalar(
        select(StructureEntry).where(StructureEntry.enzyme_entry_id == body["enzyme"]["id"])
    )
    assert structure is not None
    assert structure.structure_type == "pdb"
    assert structure.pdb_id == "1ABC"
    assert structure.source == "rcsb_mock"
    assert structure.chain_summary["provenance"]["provider"] == "rcsb_mock"


def test_enzyme_search_uses_real_uniprot_reviewed_status(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FakeUniProtClient:
        source = "uniprot"

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_keyword(self, keyword: str, size: int = 5):
            return []

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            return UniProtEntry(
                accession=accession,
                protein_name="Unreviewed UniProt enzyme",
                organism="Bacillus testingensis",
                sequence="MNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
                reviewed=False,
                cross_references={},
            )

        def fetch_fasta(self, accession: str):
            return f">tr|{accession}|UNREVIEWED\nMNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN\n"

        def fetch_cross_references(self, accession: str):
            return {}

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: FakeUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "unreviewed-uniprot@example.com",
            "password": "search-password",
            "display_name": "Unreviewed UniProt Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "unreviewed-uniprot@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "A0A999"},
    )

    assert response.status_code == 200
    assert response.json()["enzyme"]["uniprot_reviewed"] is False


def test_enzyme_search_skips_alphafold_structure_when_real_provider_fails_without_mock_fallback(
    client,
    db_session,
    monkeypatch,
):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FakeUniProtClient:
        source = "uniprot_mock"

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_keyword(self, keyword: str, size: int = 5):
            return []

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            return UniProtEntry(
                accession=accession,
                protein_name="AlphaFold fallback linked enzyme",
                organism="Bacillus testingensis",
                sequence="MNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
                cross_references={"AlphaFoldDB": "AF-P99997-F1"},
            )

        def fetch_fasta(self, accession: str):
            return ">sp|P99997|MOCK\nMNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN\n"

        def fetch_cross_references(self, accession: str):
            return {"AlphaFoldDB": "AF-P99997-F1"}

    class FailingAlphaFoldClient:
        source = "alphafold"

        def fetch_model_by_uniprot(self, uniprot_id: str):
            raise httpx.ConnectError("alphafold offline")

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: FakeUniProtClient(),
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_alphafold_client",
        lambda: FailingAlphaFoldClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "alphafold-failure@example.com",
            "password": "search-password",
            "display_name": "AlphaFold Failure Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "alphafold-failure@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P99997"},
    )

    assert response.status_code == 200
    body = response.json()
    structure = db_session.scalar(
        select(StructureEntry).where(StructureEntry.enzyme_entry_id == body["enzyme"]["id"])
    )
    assert structure is None


def test_enzyme_search_saves_literature_metadata_for_external_hit(
    client,
    db_session,
    monkeypatch,
):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FakeUniProtClient:
        source = "uniprot_mock"

        def search_by_ec(self, ec_number: str, size: int = 5):
            return []

        def search_by_keyword(self, keyword: str, size: int = 5):
            return [
                UniProtSearchHit(
                    accession="MOCKMTG1",
                    protein_name="Mock microbial transglutaminase",
                    organism="Streptomyces mobaraensis",
                    ec_number="2.3.2.13",
                )
            ]

        def search_by_organism(self, organism: str, size: int = 5):
            return []

        def fetch_entry(self, accession: str):
            return UniProtEntry(
                accession=accession,
                protein_name="Mock microbial transglutaminase",
                organism="Streptomyces mobaraensis",
                ec_number="2.3.2.13",
                sequence="MNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
                cross_references={},
            )

        def fetch_fasta(self, accession: str):
            return ">sp|MOCKMTG1|MOCK\nMNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN\n"

        def fetch_cross_references(self, accession: str):
            return {}

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_uniprot_client",
        lambda: FakeUniProtClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "literature-connector@example.com",
            "password": "search-password",
            "display_name": "Literature Connector Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "literature-connector@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "microbial transglutaminase"},
    )

    assert response.status_code == 200
    reference = db_session.scalar(
        select(LiteratureReference).where(
            LiteratureReference.doi == "10.0000/mock-mtgase-thermostability"
        )
    )
    assert reference is not None
    assert reference.source == "literature_mock"
    assert "thermostability" in reference.metadata_json["abstract"].lower()


def test_enzyme_search_skips_literature_when_real_provider_fails_without_mock_fallback(
    client,
    db_session,
    monkeypatch,
):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    class FailingLiteratureClient:
        source = "crossref"

        def search_by_enzyme_name(self, enzyme_name: str, size: int = 5):
            raise httpx.ConnectError("crossref offline")

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.routes.enzymes.get_literature_client",
        lambda: FailingLiteratureClient(),
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "literature-failure@example.com",
            "password": "search-password",
            "display_name": "Literature Failure Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "literature-failure@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "microbial transglutaminase"},
    )

    assert response.status_code == 200
    assert db_session.scalar(select(LiteratureReference).where(LiteratureReference.source == "literature_mock")) is None


def test_enzyme_search_saves_external_enzyme_data_records(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_homology_collection",
        PlaceholderTask,
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "enzyme-data-searcher@example.com",
            "password": "search-password",
            "display_name": "Enzyme Data Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "enzyme-data-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "microbial transglutaminase"},
    )

    assert response.status_code == 200
    enzyme_id = response.json()["enzyme"]["id"]

    properties = list(
        db_session.scalars(
            select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme_id)
        )
    )
    kinetics = list(
        db_session.scalars(select(KineticRecord).where(KineticRecord.enzyme_entry_id == enzyme_id))
    )
    mutations = list(
        db_session.scalars(select(MutationRecord).where(MutationRecord.enzyme_entry_id == enzyme_id))
    )

    assert {(record.property_type, record.value_original) for record in properties} == {
        ("optimal_temperature", "55"),
        ("optimal_pH", "7.0"),
        ("specific_activity", "120"),
    }
    assert all(record.evidence_text for record in properties)
    assert len(kinetics) == 1
    assert kinetics[0].substrate == "CBZ-Gln-Gly"
    assert kinetics[0].km == "2.1"
    assert kinetics[0].kcat == "31.0"
    assert kinetics[0].evidence_text == "Mock SABIO-RK-style kinetic parameter record"
    assert len(mutations) == 1
    assert mutations[0].mutation_string == "S2P"
    assert mutations[0].property_delta == {"optimal_temperature_delta_degC": 5}
