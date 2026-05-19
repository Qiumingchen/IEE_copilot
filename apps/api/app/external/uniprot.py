from dataclasses import dataclass, field

import httpx


MOCK_MTGASE_SEQUENCE = (
    "AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNGDKVTVEQSNNGTVVQSPY"
    "GAGDTVTYNGQTVTTVNAGYTVTVDKNGKTYVTLTDDKNGKTYVSVTGGDAKQAGVYAVTQG"
)
MOCK_AQGT_SEQUENCE = "MSTGTSVTPAPATTPAQPGDDVLLVGTGGTYAGALAARLGADAVVVADLPGDPARAARALAEAG"


@dataclass(frozen=True)
class UniProtSearchHit:
    accession: str
    protein_name: str
    organism: str | None = None
    ec_number: str | None = None
    score: float | None = None


@dataclass(frozen=True)
class UniProtEntry:
    accession: str
    protein_name: str
    organism: str | None = None
    ec_number: str | None = None
    sequence: str | None = None
    cross_references: dict[str, str] = field(default_factory=dict)


def parse_fasta_sequence(fasta: str) -> str:
    return "".join(line.strip() for line in fasta.splitlines() if line and not line.startswith(">"))


class MockUniProtClient:
    source = "uniprot_mock"

    def search_by_keyword(self, keyword: str, size: int = 5) -> list[UniProtSearchHit]:
        lowered = keyword.lower()
        if "anthraquinone" in lowered or "glycosyltransferase" in lowered:
            return [
                UniProtSearchHit(
                    accession="MOCKAQGT1",
                    protein_name="Mock anthraquinone glycosyltransferase",
                    organism="Streptomyces mockensis",
                    ec_number=None,
                    score=1.0,
                )
            ][:size]
        return [
            UniProtSearchHit(
                accession="MOCKMTG1",
                protein_name="Mock microbial transglutaminase",
                organism="Streptomyces mobaraensis",
                ec_number="2.3.2.13",
                score=1.0,
            )
        ][:size]

    def search_by_ec(self, ec_number: str, size: int = 5) -> list[UniProtSearchHit]:
        return [
            UniProtSearchHit(
                accession=f"MOCKEC{ec_number.replace('.', '')}",
                protein_name="Mock EC-linked microbial transglutaminase",
                organism="Streptomyces mobaraensis",
                ec_number=ec_number,
                score=1.0,
            )
        ][:size]

    def search_by_organism(self, organism: str, size: int = 5) -> list[UniProtSearchHit]:
        return [
            UniProtSearchHit(
                accession="MOCKORG1",
                protein_name="Mock organism-linked enzyme",
                organism=organism,
                ec_number=None,
                score=0.8,
            )
        ][:size]

    def fetch_entry(self, accession: str) -> UniProtEntry:
        sequence = MOCK_AQGT_SEQUENCE if "AQGT" in accession.upper() else MOCK_MTGASE_SEQUENCE
        protein_name = (
            "Mock anthraquinone glycosyltransferase"
            if "AQGT" in accession.upper()
            else "Mock microbial transglutaminase"
        )
        ec_number = None if "AQGT" in accession.upper() else "2.3.2.13"
        return UniProtEntry(
            accession=accession,
            protein_name=protein_name,
            organism="Streptomyces mobaraensis",
            ec_number=ec_number,
            sequence=sequence,
            cross_references=self.fetch_cross_references(accession),
        )

    def fetch_fasta(self, accession: str) -> str:
        sequence = self.fetch_entry(accession).sequence or MOCK_MTGASE_SEQUENCE
        return f">sp|{accession}|MOCK\n{sequence}\n"

    def fetch_cross_references(self, accession: str) -> dict[str, str]:
        return {
            "UniProtKB": accession,
            "AlphaFoldDB": f"AF-{accession}-F1",
        }


def get_uniprot_client() -> MockUniProtClient:
    return MockUniProtClient()


class UniProtClient:
    base_url = "https://rest.uniprot.org"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def search(self, query: str, size: int = 5) -> dict:
        params = {"query": query, "format": "json", "size": size}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/uniprotkb/search", params=params)
            response.raise_for_status()
            return response.json()

    async def fetch_fasta(self, accession: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/uniprotkb/{accession}.fasta")
            response.raise_for_status()
            return response.text
