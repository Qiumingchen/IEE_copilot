from datetime import datetime, timedelta

from sqlalchemy import select

from app.db.models import (
    AnalysisJob,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    ProteinSequence,
    SearchCacheRecord,
    StructureEntry,
)
from app.external.uniprot import UniProtEntry, UniProtSearchHit
from app.services.cache import DATA_MODULE_SEQUENCE, DATA_MODULE_STRUCTURE


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
    assert structure.chain_summary == {"polymer_entity_count": 1, "chains": ["A"]}
    assert structure.ligand_summary == {"ligands": ["GTP"]}


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
