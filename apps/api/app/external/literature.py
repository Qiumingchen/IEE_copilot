from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LiteratureReference


@dataclass(frozen=True)
class LiteratureMetadata:
    title: str
    authors: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pubmed_id: str | None = None
    abstract: str | None = None
    source: str = "literature_mock"
    metadata: dict = field(default_factory=dict)


class MockLiteratureClient:
    source = "literature_mock"

    def search_pubmed_metadata(self, pubmed_id: str) -> LiteratureMetadata | None:
        for item in MOCK_LITERATURE:
            if item.pubmed_id == pubmed_id:
                return item
        return None

    def search_by_enzyme_name(self, enzyme_name: str, size: int = 5) -> list[LiteratureMetadata]:
        lowered = enzyme_name.lower()
        if "anthraquinone" in lowered or "glycosyltransferase" in lowered:
            return [MOCK_AQGT_LITERATURE][:size]
        return [MOCK_MTGASE_PROPERTY_LITERATURE][:size]

    def search_by_mutation_keyword(self, keyword: str, size: int = 5) -> list[LiteratureMetadata]:
        lowered = keyword.lower()
        if "mutation" in lowered or "mutant" in lowered or any(char.isdigit() for char in keyword):
            return [MOCK_MTGASE_MUTANT_LITERATURE][:size]
        return self.search_by_enzyme_name(keyword, size=size)


def get_literature_client() -> MockLiteratureClient:
    return MockLiteratureClient()


def create_literature_reference(db: Session, metadata: LiteratureMetadata) -> LiteratureReference:
    existing = None
    if metadata.doi:
        existing = db.scalar(select(LiteratureReference).where(LiteratureReference.doi == metadata.doi))
    if existing is None and metadata.pubmed_id:
        existing = db.scalar(
            select(LiteratureReference).where(LiteratureReference.pubmed_id == metadata.pubmed_id)
        )
    if existing is not None:
        return existing

    metadata_json = dict(metadata.metadata)
    if metadata.abstract is not None:
        metadata_json["abstract"] = metadata.abstract

    reference = LiteratureReference(
        title=metadata.title,
        authors=metadata.authors,
        journal=metadata.journal,
        year=metadata.year,
        doi=metadata.doi,
        pubmed_id=metadata.pubmed_id,
        source=metadata.source,
        metadata_json=metadata_json or None,
    )
    db.add(reference)
    db.flush()
    return reference


MOCK_MTGASE_PROPERTY_LITERATURE = LiteratureMetadata(
    title="Mock thermostability study of microbial transglutaminase",
    authors="Q. Tester; E. Engineer",
    journal="Journal of Mock Enzyme Engineering",
    year=2026,
    doi="10.0000/mock-mtgase-thermostability",
    pubmed_id="10000001",
    abstract="Mock study reporting thermostability, optimal temperature, optimal pH, and activity.",
    metadata={"topics": ["thermostability", "optimal_temperature", "specific_activity"]},
)

MOCK_MTGASE_MUTANT_LITERATURE = LiteratureMetadata(
    title="Mock mutant landscape of microbial transglutaminase",
    authors="M. Variant; E. Engineer",
    journal="Journal of Mock Protein Design",
    year=2026,
    doi="10.0000/mock-mtgase-mutants",
    pubmed_id="10000003",
    abstract="Mock mutation study including S2P, D3Y, and combined thermostability variants.",
    metadata={"topics": ["mutation", "thermostability"]},
)

MOCK_AQGT_LITERATURE = LiteratureMetadata(
    title="Mock anthraquinone glycosyltransferase substrate scope",
    authors="A. Glyco; Q. Tester",
    journal="Journal of Mock Natural Product Biocatalysis",
    year=2026,
    doi="10.0000/mock-aqgt-substrate-scope",
    pubmed_id="10000004",
    abstract="Mock study describing anthraquinone substrate specificity and glycosylation selectivity.",
    metadata={"topics": ["anthraquinone", "substrate_specificity"]},
)

MOCK_LITERATURE = (
    MOCK_MTGASE_PROPERTY_LITERATURE,
    MOCK_MTGASE_MUTANT_LITERATURE,
    MOCK_AQGT_LITERATURE,
)


class LiteratureClient:
    async def search_metadata(self, query: str) -> list[dict]:
        client = get_literature_client()
        return [item.__dict__ for item in client.search_by_enzyme_name(query)]
