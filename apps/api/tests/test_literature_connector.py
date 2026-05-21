from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import LiteratureReference
from app.external.literature import (
    LiteratureMetadata,
    MockLiteratureClient,
    RealLiteratureClient,
    create_literature_reference,
    get_literature_client,
    parse_crossref_item,
)


def test_mock_literature_search_by_enzyme_name_returns_metadata():
    client = MockLiteratureClient()

    hits = client.search_by_enzyme_name("microbial transglutaminase")

    assert len(hits) == 1
    assert hits[0].title == "Mock thermostability study of microbial transglutaminase"
    assert hits[0].doi == "10.0000/mock-mtgase-thermostability"
    assert hits[0].pubmed_id == "10000001"
    assert "thermostability" in hits[0].abstract.lower()


def test_mock_literature_search_by_mutation_keyword_returns_mutant_metadata():
    client = MockLiteratureClient()

    hits = client.search_by_mutation_keyword("S2P microbial transglutaminase")

    assert len(hits) == 1
    assert hits[0].title == "Mock mutant landscape of microbial transglutaminase"
    assert hits[0].doi == "10.0000/mock-mtgase-mutants"
    assert "S2P" in hits[0].abstract


def test_mock_literature_search_pubmed_metadata_returns_pubmed_hit():
    client = MockLiteratureClient()

    hit = client.search_pubmed_metadata("10000001")

    assert hit is not None
    assert hit.pubmed_id == "10000001"
    assert hit.journal == "Journal of Mock Enzyme Engineering"


def test_create_literature_reference_saves_metadata_and_deduplicates_by_doi(db_session):
    metadata = LiteratureMetadata(
        title="A reusable mock literature reference",
        authors="Q. Tester; E. Engineer",
        journal="Journal of Mock Enzyme Engineering",
        year=2026,
        doi="10.0000/mock-reusable",
        pubmed_id="10000002",
        abstract="Reusable mock abstract",
        source="literature_mock",
        metadata={"query": "reusable"},
    )

    first = create_literature_reference(db_session, metadata)
    second = create_literature_reference(db_session, metadata)
    db_session.commit()

    references = list(
        db_session.scalars(
            select(LiteratureReference).where(LiteratureReference.doi == "10.0000/mock-reusable")
        )
    )
    assert first.id == second.id
    assert len(references) == 1
    assert references[0].metadata_json["abstract"] == "Reusable mock abstract"
    assert references[0].metadata_json["query"] == "reusable"


def test_parse_crossref_item_extracts_literature_metadata():
    item = {
        "title": ["Enzyme engineering by mutation"],
        "author": [{"given": "Ada", "family": "Lovelace"}, {"given": "Q", "family": "Tester"}],
        "container-title": ["Biocatalysis Reports"],
        "published-print": {"date-parts": [[2025, 1, 1]]},
        "DOI": "10.1000/example",
        "abstract": "<jats:p>Reports variants.</jats:p>",
    }

    metadata = parse_crossref_item(item)

    assert metadata.title == "Enzyme engineering by mutation"
    assert metadata.authors == "Ada Lovelace; Q Tester"
    assert metadata.journal == "Biocatalysis Reports"
    assert metadata.year == 2025
    assert metadata.doi == "10.1000/example"
    assert metadata.source == "crossref"
    assert metadata.metadata["provider"] == "crossref"
    assert metadata.metadata["provenance"]["provider"] == "crossref"
    assert metadata.metadata["provenance"]["mode"] == "real"
    assert metadata.metadata["provenance"]["source_url"] == "https://doi.org/10.1000/example"
    assert metadata.metadata["provenance"]["retrieved_at"].endswith("Z")


def test_create_literature_reference_persists_crossref_provenance(db_session):
    item = {
        "title": ["Traceable enzyme engineering"],
        "DOI": "10.1000/traceable",
        "abstract": "<jats:p>Traceable record.</jats:p>",
    }
    metadata = parse_crossref_item(item)

    reference = create_literature_reference(db_session, metadata)
    db_session.commit()

    assert reference.metadata_json["provider"] == "crossref"
    assert reference.metadata_json["abstract"] == "<jats:p>Traceable record.</jats:p>"
    assert reference.metadata_json["provenance"]["mode"] == "real"
    assert reference.metadata_json["provenance"]["source_url"] == "https://doi.org/10.1000/traceable"


def test_get_literature_client_returns_real_client_when_enabled(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")

    assert isinstance(get_literature_client(), RealLiteratureClient)
    get_settings.cache_clear()
