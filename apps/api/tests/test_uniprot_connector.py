from app.external.uniprot import MockUniProtClient, parse_fasta_sequence


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
