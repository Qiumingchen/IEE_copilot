from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from app.db.models import (
    AnalysisJob,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    ExpressionRecord,
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
from app.external.enzyme_data import ExternalKineticParameter, ExternalMutantRecord, ExternalPropertyDatum
from app.external.literature import LiteratureMetadata
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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


def test_real_provider_search_does_not_create_seed_entry_when_no_real_hit(client, db_session, monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
                    source=self.source,
                    evidence="Europe PMC PMID:123 optimum temperature",
                )
            ]

        def fetch_opt_pH(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_pH",
                    value_original="7.5",
                    source=self.source,
                    evidence="Europe PMC PMID:123 optimum pH",
                )
            ]

        def fetch_kinetic_parameters(self, query: str, size: int = 5):
            return [
                ExternalKineticParameter(
                    substrate="casein",
                    km="1.8",
                    kcat="24.0",
                    unit_original="mM; s^-1",
                    source=self.source,
                    evidence="Europe PMC PMID:123 kinetic parameters",
                )
            ]

        def fetch_mutants(self, query: str, size: int = 5):
            return [
                ExternalMutantRecord(
                    mutation_string="A10V",
                    effect_summary="Real literature mention: A10V improved thermostability.",
                    source=self.source,
                    evidence="Europe PMC PMID:123 mutant",
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
    assert body["created"] == {"references": 1, "properties": 2, "kinetics": 1, "mutations": 1, "structures": 0}
    assert body["sources"] == ["crossref", "europepmc"]

    properties = db_session.scalars(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme.id)).all()
    kinetics = db_session.scalars(select(KineticRecord).where(KineticRecord.enzyme_entry_id == enzyme.id)).all()
    mutations = db_session.scalars(select(MutationRecord).where(MutationRecord.enzyme_entry_id == enzyme.id)).all()
    references = db_session.scalars(select(LiteratureReference)).all()
    assert {record.method for record in properties} == {"europepmc"}
    assert kinetics[0].method == "europepmc"
    assert mutations[0].assay_condition_summary["source"] == "europepmc"
    assert references[0].source == "crossref"


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


def test_family_real_data_refresh_updates_same_family_entries(client, db_session, monkeypatch):
    class RealDataClient:
        source = "europepmc"

        def fetch_opt_temperature(self, query: str, size: int = 5):
            return [
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original=f"{query} 62",
                    unit_original="degC",
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


def test_enzyme_search_reuses_fresh_search_cache(client, db_session, monkeypatch):
    enqueued_job_ids = []

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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


def test_enzyme_search_refreshes_stale_local_pdb_match(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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

    class FakeUniProtClient:
        source = "uniprot"

        def search_by_ec(self, ec_number: str, size: int = 5):
            raise AssertionError("keyword search should not call EC search")

        def search_by_keyword(self, keyword: str, size: int = 5):
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

    monkeypatch.setattr("app.api.routes.enzymes.run_placeholder_analysis", PlaceholderTask, raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_uniprot_client", lambda: FakeUniProtClient(), raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_alphafold_client", lambda: EmptyAlphaFoldClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_literature_client", lambda: EmptyLiteratureClient())
    monkeypatch.setattr("app.api.routes.enzymes.get_enzyme_data_client", lambda: EmptyEnzymeDataClient())

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
    assert [match["uniprot_id"] for match in body["matches"]] == ["R11111", "R22222", "R33333"]
    assert {match["source"] for match in body["matches"]} == {"uniprot"}
    assert body["enzyme"]["uniprot_id"] == "R11111"
    assert (
        db_session.scalar(select(EnzymeEntry).where(EnzymeEntry.uniprot_id == "R33333"))
        is not None
    )


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

    monkeypatch.setattr("app.api.routes.enzymes.run_placeholder_analysis", PlaceholderTask, raising=False)
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

    monkeypatch.setattr("app.api.routes.enzymes.run_placeholder_analysis", PlaceholderTask, raising=False)
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
        "app.api.routes.enzymes.run_placeholder_analysis",
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
