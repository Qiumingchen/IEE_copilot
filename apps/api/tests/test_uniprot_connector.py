from app.core.config import get_settings
from app.external.uniprot import (
    MockUniProtClient,
    RealUniProtClient,
    parse_fasta_sequence,
    parse_uniprot_entry_payload,
)


def test_mock_uniprot_search_by_keyword_returns_structured_hit():
    client = MockUniProtClient()

    hits = client.search_by_keyword("microbial transglutaminase")

    assert hits
    assert hits[0].accession.startswith("MOCK")
    assert hits[0].protein_name
    assert hits[0].organism


def test_mock_uniprot_search_by_ec_returns_ec_annotated_hit():
    client = MockUniProtClient()

    hits = client.search_by_ec("2.3.2.13")

    assert hits
    assert hits[0].ec_number == "2.3.2.13"


def test_mock_uniprot_fetch_entry_and_fasta_share_accession():
    client = MockUniProtClient()

    entry = client.fetch_entry("P81453")
    fasta = client.fetch_fasta("P81453")

    assert entry.accession == "P81453"
    assert fasta.startswith(">sp|P81453|")
    assert parse_fasta_sequence(fasta)


def test_mock_uniprot_fetch_cross_references_includes_structure_sources():
    client = MockUniProtClient()

    cross_references = client.fetch_cross_references("P81453")

    assert cross_references["UniProtKB"] == "P81453"
    assert "AlphaFoldDB" in cross_references


def test_parse_uniprot_entry_payload_extracts_core_fields():
    payload = {
        "primaryAccession": "P81453",
        "proteinDescription": {
            "recommendedName": {
                "fullName": {"value": "Protein-glutamine gamma-glutamyltransferase"},
                "ecNumbers": [{"value": "2.3.2.13"}],
            }
        },
        "organism": {"scientificName": "Streptomyces mobaraensis"},
        "sequence": {"value": "ACDEFG"},
        "uniProtKBCrossReferences": [
            {"database": "AlphaFoldDB", "id": "AF-P81453-F1"},
            {"database": "PDB", "id": "1IU4"},
        ],
    }

    entry = parse_uniprot_entry_payload(payload)

    assert entry.accession == "P81453"
    assert entry.protein_name == "Protein-glutamine gamma-glutamyltransferase"
    assert entry.organism == "Streptomyces mobaraensis"
    assert entry.ec_number == "2.3.2.13"
    assert entry.sequence == "ACDEFG"
    assert entry.cross_references["AlphaFoldDB"] == "AF-P81453-F1"
    assert entry.cross_references["PDB"] == "1IU4"


def test_get_uniprot_client_returns_real_client_when_enabled(monkeypatch):
    from app.external.uniprot import get_uniprot_client

    get_settings.cache_clear()
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")

    client = get_uniprot_client()

    assert isinstance(client, RealUniProtClient)
    assert client.source == "uniprot"
    get_settings.cache_clear()
