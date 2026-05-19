from app.external.rcsb import MockRcsbClient


def test_mock_rcsb_client_fetches_structure_metadata():
    client = MockRcsbClient()

    metadata = client.fetch_structure_metadata("1abc")

    assert metadata.pdb_id == "1ABC"
    assert metadata.title == "Mock RCSB microbial transglutaminase structure"
    assert metadata.uniprot_id == "MOCKMTG1"
    assert metadata.chain_summary == {"polymer_entity_count": 1, "chains": ["A"]}
    assert metadata.ligand_summary == {"ligands": ["GTP"]}


def test_mock_rcsb_client_searches_by_uniprot():
    client = MockRcsbClient()

    hits = client.search_by_uniprot("MOCKMTG1")

    assert hits == ["1ABC"]


def test_mock_rcsb_client_downloads_pdb_text():
    client = MockRcsbClient()

    pdb_text = client.download_pdb_or_cif("1abc")

    assert "HEADER" in pdb_text
    assert "1ABC" in pdb_text
