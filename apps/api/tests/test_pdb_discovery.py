from datetime import datetime

from app.db.models import EnzymeEntry, EnzymeFamily, EnzymeModule, ProteinSequence


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


def test_pdb_discovery_rejects_files_without_protein_sequence(client):
    token = _register_and_login(client)

    response = client.post(
        "/enzymes/discover-pdb",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("ligand.pdb", "HETATM    1  C1  LIG A   1       1.0   1.0   1.0\nEND\n", "chemical/x-pdb")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "uploaded structure does not contain a protein sequence"
