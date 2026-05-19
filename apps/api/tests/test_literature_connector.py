from sqlalchemy import select

from app.db.models import LiteratureReference
from app.external.literature import (
    LiteratureMetadata,
    MockLiteratureClient,
    create_literature_reference,
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
