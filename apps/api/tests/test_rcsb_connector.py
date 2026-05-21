from app.core.config import get_settings
from app.external.rcsb import MockRcsbClient, RealRcsbClient, get_rcsb_client, parse_rcsb_entry_payload


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


def test_parse_rcsb_entry_payload_extracts_structure_metadata():
    payload = {
        "rcsb_id": "1IU4",
        "struct": {"title": "Microbial transglutaminase structure"},
        "exptl": [{"method": "X-RAY DIFFRACTION"}],
        "rcsb_entry_info": {"resolution_combined": [2.1], "polymer_entity_count_protein": 1},
        "rcsb_entity_source_organism": [{"scientific_name": "Streptomyces mobaraensis"}],
    }

    metadata = parse_rcsb_entry_payload(payload)

    assert metadata.pdb_id == "1IU4"
    assert metadata.title == "Microbial transglutaminase structure"
    assert metadata.method == "X-RAY DIFFRACTION"
    assert metadata.resolution == 2.1
    assert metadata.organism == "Streptomyces mobaraensis"
    assert metadata.chain_summary["polymer_entity_count"] == 1


def test_get_rcsb_client_returns_real_client_when_enabled(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")

    assert isinstance(get_rcsb_client(), RealRcsbClient)
    get_settings.cache_clear()
