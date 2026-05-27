from datetime import datetime

from sqlalchemy import select

from app.db.models import EnzymeEntry, EnzymeFamily, EnzymeModule, ProteinSequence, PropertyRecord, StructureEntry
from app.external.rcsb import RcsbStructureMetadata
from app.external.uniprot import UniProtEntry


PDB_WITH_SEQUENCE = """\
HEADER    TRANSFERASE                              01-JAN-26   9XYZ
TITLE     TEST MICROBIAL TRANSGLUTAMINASE STRUCTURE
COMPND    MOL_ID: 1; MOLECULE: MICROBIAL TRANSGLUTAMINASE; CHAIN: A;
SOURCE    MOL_ID: 1; ORGANISM_SCIENTIFIC: STREPTOMYCES MOBARAENSIS;
ATOM      1  CA  ALA A   1      11.104  13.207   9.342  1.00 20.00           C
ATOM      2  CA  GLU A   2      12.560  13.407   9.142  1.00 20.00           C
ATOM      3  CA  ALA A   3      13.560  13.407   9.142  1.00 20.00           C
ATOM      4  CA  LYS A   4      14.560  13.407   9.142  1.00 20.00           C
ATOM      5  CA  LEU A   5      15.560  13.407   9.142  1.00 20.00           C
ATOM      6  CA  LEU A   6      16.560  13.407   9.142  1.00 20.00           C
ATOM      7  CA  ASN A   7      17.560  13.407   9.142  1.00 20.00           C
ATOM      8  CA  ASP A   8      18.560  13.407   9.142  1.00 20.00           C
END
"""


PDB_WITH_UNIPROT_REFERENCE = """\
HEADER    TRANSFERASE                              01-JAN-26   8ABC
TITLE     TEST MICROBIAL TRANSGLUTAMINASE STRUCTURE
COMPND    MOL_ID: 1; MOLECULE: MICROBIAL TRANSGLUTAMINASE; CHAIN: A;
SOURCE    MOL_ID: 1; ORGANISM_SCIENTIFIC: STREPTOMYCES MOBARAENSIS;
DBREF  8ABC A    1   407  UNP    P81453   TGAS_STRMB       1    407
ATOM      1  CA  ALA A   1      11.104  13.207   9.342  1.00 20.00           C
ATOM      2  CA  GLU A   2      12.560  13.407   9.142  1.00 20.00           C
ATOM      3  CA  ALA A   3      13.560  13.407   9.142  1.00 20.00           C
ATOM      4  CA  LYS A   4      14.560  13.407   9.142  1.00 20.00           C
ATOM      5  CA  LEU A   5      15.560  13.407   9.142  1.00 20.00           C
ATOM      6  CA  LEU A   6      16.560  13.407   9.142  1.00 20.00           C
ATOM      7  CA  ASN A   7      17.560  13.407   9.142  1.00 20.00           C
ATOM      8  CA  ASP A   8      18.560  13.407   9.142  1.00 20.00           C
END
"""


CIF_WITH_SEQUENCE = """\
data_query
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
ATOM 1 C CA ALA A 1 ? 11.104 13.207 9.342
ATOM 2 C CA GLU A 2 ? 12.560 13.407 9.142
ATOM 3 C CA ALA A 3 ? 13.560 13.407 9.142
ATOM 4 C CA LYS A 4 ? 14.560 13.407 9.142
ATOM 5 C CA LEU A 5 ? 15.560 13.407 9.142
ATOM 6 C CA LEU A 6 ? 16.560 13.407 9.142
ATOM 7 C CA ASN A 7 ? 17.560 13.407 9.142
ATOM 8 C CA ASP A 8 ? 18.560 13.407 9.142
#
"""


def _register_and_login(client) -> str:
    client.post(
        "/auth/register",
        json={
            "email": "pdb-discovery@example.com",
            "password": "search-password",
            "display_name": "PDB Discovery",
        },
    )
    response = client.post(
        "/auth/login",
        json={"email": "pdb-discovery@example.com", "password": "search-password"},
    )
    return response.json()["access_token"]


def test_pdb_discovery_extracts_metadata_sequence_and_local_similarity_hits(client, db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Local mTGase sequence hit",
        organism="Streptomyces mobaraensis",
        ec_number="2.3.2.13",
        source="local",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="AEAKLLND",
            mature_sequence="AEAKLLND",
            source="test",
            checksum="pdb-discovery-hit",
        )
    )
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="AEAKLLND",
            mature_sequence="AEAKLLND",
            source="test_duplicate",
            checksum="pdb-discovery-hit-duplicate",
        )
    )
    db_session.commit()
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("query.pdb", PDB_WITH_SEQUENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["file_name"] == "query.pdb"
    assert body["metadata"]["pdb_id"] == "9XYZ"
    assert body["metadata"]["title"] == "TEST MICROBIAL TRANSGLUTAMINASE STRUCTURE"
    assert body["metadata"]["organism"] == "STREPTOMYCES MOBARAENSIS"
    assert body["chains"][0]["chain_id"] == "A"
    assert body["chains"][0]["sequence"] == "AEAKLLND"
    assert body["query_sequence"] == "AEAKLLND"
    assert body["hits"][0]["enzyme"]["id"] == enzyme.id
    assert body["hits"][0]["identity"] == 1.0
    assert body["hits"][0]["coverage"] == 1.0
    assert body["hits"][0]["evidence"] == ["sequence_similarity", "local_database"]
    assert [hit["enzyme"]["id"] for hit in body["hits"]].count(enzyme.id) == 1


def test_pdb_discovery_groups_upload_with_local_enzyme_by_pdb_id(client, db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="RCSB-backed mTGase",
        organism="Streptomyces mobaraensis",
        pdb_id="9XYZ",
        source="local",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="TTTTTTTT",
            mature_sequence="TTTTTTTT",
            source="test",
            checksum="pdb-discovery-exact-id",
        )
    )
    db_session.commit()
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("9xyz.pdb", PDB_WITH_SEQUENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["pdb_id"] == "9XYZ"
    assert body["hits"][0]["enzyme"]["id"] == enzyme.id
    assert body["hits"][0]["confidence"] == "exact"
    assert body["hits"][0]["evidence"] == ["pdb_id", "local_database"]


def test_pdb_discovery_groups_upload_with_local_enzyme_by_alphafold_id(client, db_session):
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
        alphafold_id="AF-P81453-F1",
        source="local",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="TTTTTTTT",
            mature_sequence="TTTTTTTT",
            source="test",
            checksum="pdb-discovery-exact-alphafold-id",
        )
    )
    db_session.commit()
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("AF-P81453-F1-model_v4.pdb", PDB_WITH_SEQUENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["alphafold_id"] == "AF-P81453-F1"
    assert body["hits"][0]["enzyme"]["id"] == enzyme.id
    assert body["hits"][0]["confidence"] == "exact"
    assert body["hits"][0]["evidence"] == ["alphafold_id", "local_database"]


def test_pdb_discovery_matches_uniprot_id_case_insensitively(client, db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="UniProt-backed mTGase",
        organism="Streptomyces mobaraensis",
        uniprot_id="p81453",
        source="local",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("rcsb-with-uniprot.pdb", PDB_WITH_UNIPROT_REFERENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["uniprot_id"] == "P81453"
    assert body["hits"][0]["enzyme"]["id"] == enzyme.id
    assert body["hits"][0]["confidence"] == "exact"
    assert body["hits"][0]["evidence"] == ["uniprot_id", "local_database"]


def test_pdb_discovery_preserves_sequence_metrics_for_identifier_matches(client, db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="UniProt-backed sequence mTGase",
        organism="Streptomyces mobaraensis",
        uniprot_id="P81453",
        source="local",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="AEAKLLNE",
            mature_sequence="AEAKLLNE",
            source="test",
            checksum="pdb-discovery-uniprot-sequence-metrics",
        )
    )
    db_session.commit()
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("rcsb-with-uniprot.pdb", PDB_WITH_UNIPROT_REFERENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["hits"][0]["enzyme"]["id"] == enzyme.id
    assert body["hits"][0]["confidence"] == "exact"
    assert body["hits"][0]["identity"] == 0.875
    assert body["hits"][0]["coverage"] == 1.0
    assert body["hits"][0]["evidence"] == ["uniprot_id", "sequence_similarity", "local_database"]


def test_pdb_discovery_searches_across_enzyme_families_without_module_selection(client, db_session):
    mtgase_family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    aqgt_family = EnzymeFamily(
        module=EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE,
        name="Anthraquinone glycosyltransferases",
    )
    db_session.add_all([mtgase_family, aqgt_family])
    db_session.flush()
    mtgase_enzyme = EnzymeEntry(
        family_id=mtgase_family.id,
        name="mTGase lookalike",
        organism="Streptomyces mobaraensis",
        source="local",
        last_refreshed_at=datetime.utcnow(),
    )
    aqgt_enzyme = EnzymeEntry(
        family_id=aqgt_family.id,
        name="AQGT selected module hit",
        organism="Streptomyces sp.",
        source="local",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add_all([mtgase_enzyme, aqgt_enzyme])
    db_session.flush()
    db_session.add_all(
        [
            ProteinSequence(
                enzyme_entry_id=mtgase_enzyme.id,
                sequence="AEAKLLND",
                mature_sequence="AEAKLLND",
                source="test",
                checksum="pdb-discovery-module-mtgase",
            ),
            ProteinSequence(
                enzyme_entry_id=aqgt_enzyme.id,
                sequence="AEAKLLND",
                mature_sequence=None,
                source="test",
                checksum="pdb-discovery-module-aqgt",
            ),
        ]
    )
    db_session.commit()
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("query.pdb", PDB_WITH_SEQUENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert {hit["enzyme"]["id"] for hit in body["hits"]} == {mtgase_enzyme.id, aqgt_enzyme.id}


def test_pdb_discovery_orders_comparable_hits_by_reviewed_temperature_and_activity(client, db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Food processing amylases",
    )
    db_session.add(family)
    db_session.flush()
    reviewed = EnzymeEntry(
        family_id=family.id,
        name="PDB ranked reviewed enzyme",
        organism="Bacillus subtilis",
        uniprot_id="P00691",
        uniprot_reviewed=True,
        source="uniprot",
        last_refreshed_at=datetime.utcnow(),
    )
    hot = EnzymeEntry(
        family_id=family.id,
        name="PDB ranked hot enzyme",
        organism="Geobacillus stearothermophilus",
        source="curated_literature",
        last_refreshed_at=datetime.utcnow(),
    )
    active = EnzymeEntry(
        family_id=family.id,
        name="PDB ranked active enzyme",
        organism="Aspergillus oryzae",
        source="curated_literature",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add_all([active, hot, reviewed])
    db_session.flush()
    for enzyme, checksum in [
        (active, "pdb-ranked-active"),
        (hot, "pdb-ranked-hot"),
        (reviewed, "pdb-ranked-reviewed"),
    ]:
        db_session.add(
            ProteinSequence(
                enzyme_entry_id=enzyme.id,
                sequence="AEAKLLND",
                mature_sequence="AEAKLLND",
                source="test",
                checksum=checksum,
            )
        )
    db_session.add_all(
        [
            PropertyRecord(
                enzyme_entry_id=hot.id,
                property_type="optimal_temperature",
                value_original="90",
                unit_original="degC",
                value_standardized="90",
                unit_standardized="degC",
                standardization_status="standardized",
            ),
            PropertyRecord(
                enzyme_entry_id=active.id,
                property_type="optimal_temperature",
                value_original="50",
                unit_original="degC",
                value_standardized="50",
                unit_standardized="degC",
                standardization_status="standardized",
            ),
            PropertyRecord(
                enzyme_entry_id=active.id,
                property_type="specific_activity",
                value_original="1200",
                unit_original="U/mg",
                value_standardized="1200",
                unit_standardized="U/mg",
                standardization_status="standardized",
            ),
        ]
    )
    db_session.commit()
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("query.pdb", PDB_WITH_SEQUENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    hits = response.json()["hits"]
    ordered_ids = [hit["enzyme"]["id"] for hit in hits[:3]]
    assert ordered_ids == [reviewed.id, hot.id, active.id]
    assert hits[0]["enzyme"]["uniprot_reviewed"] is True
    assert hits[1]["enzyme"]["optimal_temperature"] == 90.0
    assert hits[2]["enzyme"]["specific_activity"] == 1200.0


def test_pdb_discovery_accepts_mmcif_extension(client, db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="mmCIF mTGase hit",
        organism="Streptomyces mobaraensis",
        source="local",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="AEAKLLND",
            mature_sequence="AEAKLLND",
            source="test",
            checksum="pdb-discovery-mmcif",
        )
    )
    db_session.commit()
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("query.mmcif", CIF_WITH_SEQUENCE, "chemical/x-cif")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["structure_type"] == "uploaded_cif"
    assert body["hits"][0]["enzyme"]["id"] == enzyme.id


def test_pdb_discovery_matches_alphafold_file_name_to_accession_style_local_id(client, db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="AlphaFold accession-backed mTGase",
        organism="Streptomyces mobaraensis",
        alphafold_id="P81453",
        source="local",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.commit()
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("AF-P81453-F1-model_v4.pdb", PDB_WITH_SEQUENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["alphafold_id"] == "AF-P81453-F1"
    assert body["hits"][0]["enzyme"]["id"] == enzyme.id
    assert body["hits"][0]["confidence"] == "exact"
    assert body["hits"][0]["evidence"] == ["alphafold_id", "local_database"]


def test_pdb_discovery_groups_upload_with_structure_level_alphafold_id(client, db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Structure-level AlphaFold mTGase",
        organism="Streptomyces mobaraensis",
        source="local",
        last_refreshed_at=datetime.utcnow(),
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        StructureEntry(
            enzyme_entry_id=enzyme.id,
            structure_type="uploaded_pdb",
            complex_state="apo",
            chain_summary={
                "identifiers": {
                    "alphafold_id": "AF-P81453-F1",
                    "uniprot_id": "P81453",
                }
            },
            source="user_upload",
        )
    )
    db_session.commit()
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("AF-P81453-F1-model_v6.pdb", PDB_WITH_SEQUENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["hits"][0]["enzyme"]["id"] == enzyme.id
    assert body["hits"][0]["confidence"] == "exact"
    assert body["hits"][0]["evidence"] == ["alphafold_id", "local_database"]


def test_pdb_discovery_fetches_remote_uniprot_from_alphafold_filename_when_not_local(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RemoteUniProtClient:
        source = "uniprot"
        fetch_entry_calls: list[str] = []

        def fetch_entry(self, accession: str):
            self.fetch_entry_calls.append(accession)
            assert accession == "P81453"
            return UniProtEntry(
                accession="P81453",
                protein_name="Protein-glutamine gamma-glutamyltransferase",
                organism="Streptomyces mobaraensis",
                ec_number="2.3.2.13",
                sequence="AEAKLLND",
                mature_sequence="AEAKLLND",
                reviewed=True,
                cross_references={"AlphaFoldDB": "AF-P81453-F1"},
            )

        def fetch_fasta(self, accession: str):
            raise AssertionError("sequence is already present on remote UniProt entry")

    uniprot_client = RemoteUniProtClient()
    monkeypatch.setattr("app.api.routes.enzymes.get_uniprot_client", lambda: uniprot_client, raising=False)
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("AF-P81453-F1-model_v6.pdb", PDB_WITH_SEQUENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["alphafold_id"] == "AF-P81453-F1"
    assert body["metadata"]["uniprot_id"] == "P81453"
    assert body["hits"][0]["enzyme"]["uniprot_id"] == "P81453"
    assert body["hits"][0]["enzyme"]["alphafold_id"] == "AF-P81453-F1"
    assert body["hits"][0]["identity"] == 1.0
    assert body["hits"][0]["coverage"] == 1.0
    assert body["hits"][0]["confidence"] == "exact"
    assert body["hits"][0]["evidence"] == ["alphafold_id", "remote_database"]
    assert uniprot_client.fetch_entry_calls == ["P81453"]
    assert db_session.scalar(select(EnzymeEntry).where(EnzymeEntry.uniprot_id == "P81453")) is not None


def test_pdb_discovery_fetches_remote_uniprot_from_rcsb_pdb_id_when_not_local(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class RemoteRcsbClient:
        source = "rcsb"
        fetch_calls: list[str] = []

        def fetch_structure_metadata(self, pdb_id: str):
            self.fetch_calls.append(pdb_id)
            assert pdb_id == "9XYZ"
            return RcsbStructureMetadata(
                pdb_id="9XYZ",
                title="Remote microbial transglutaminase",
                method="X-ray diffraction",
                resolution=2.1,
                uniprot_id="P81453",
                organism="Streptomyces mobaraensis",
                chain_summary={"A": {"length": 8}},
                ligand_summary=[],
            )

    class RemoteUniProtClient:
        source = "uniprot"
        fetch_entry_calls: list[str] = []

        def fetch_entry(self, accession: str):
            self.fetch_entry_calls.append(accession)
            assert accession == "P81453"
            return UniProtEntry(
                accession="P81453",
                protein_name="Protein-glutamine gamma-glutamyltransferase",
                organism="Streptomyces mobaraensis",
                ec_number="2.3.2.13",
                sequence="AEAKLLND",
                mature_sequence="AEAKLLND",
                reviewed=True,
                cross_references={"PDB": "9XYZ", "AlphaFoldDB": "AF-P81453-F1"},
            )

        def fetch_fasta(self, accession: str):
            raise AssertionError("sequence is already present on remote UniProt entry")

    rcsb_client = RemoteRcsbClient()
    uniprot_client = RemoteUniProtClient()
    monkeypatch.setattr("app.api.routes.enzymes.get_rcsb_client", lambda: rcsb_client, raising=False)
    monkeypatch.setattr("app.api.routes.enzymes.get_uniprot_client", lambda: uniprot_client, raising=False)
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("9xyz.pdb", PDB_WITH_SEQUENCE, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["pdb_id"] == "9XYZ"
    assert body["metadata"]["uniprot_id"] == "P81453"
    assert body["hits"][0]["enzyme"]["uniprot_id"] == "P81453"
    assert body["hits"][0]["enzyme"]["pdb_id"] == "9XYZ"
    assert body["hits"][0]["confidence"] == "exact"
    assert body["hits"][0]["evidence"] == ["pdb_id", "remote_database"]
    assert rcsb_client.fetch_calls == ["9XYZ"]
    assert uniprot_client.fetch_entry_calls == ["P81453"]
    assert db_session.scalar(select(EnzymeEntry).where(EnzymeEntry.uniprot_id == "P81453")) is not None


def test_pdb_discovery_rejects_files_without_protein_sequence(client):
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("ligand.pdb", "HETATM    1  C1  LIG A   1       1.0   1.0   1.0\nEND\n", "chemical/x-pdb")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "uploaded structure does not contain a protein sequence"
