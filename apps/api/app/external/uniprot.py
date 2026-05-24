from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings
from app.services.provenance import build_real_provenance


P81453_FULL_SEQUENCE = (
    "MRIRRRALVFATMSAVLCTAGFMPSAGEAAADNGAGEETKSYAETYRLTADDVANINALNESAPAASSAGPSFRAP"
    "DSDDRVTPPAEPLDRMPDPYRPSYGRAETVVNNYIRKWQQVYSHRDGRKQQMTEEQREWLSYGCVGVTWVNSGQYP"
    "TNRLAFASFDEDRFKNELKNGRPRSGETRAEFEGRVAKESFDEEKGFQRAREVASVMNRALENAHDESAYLDNLKK"
    "ELANGNDALRNEDARSPFYSALRNTPSFKERNGGNHDPSRMKAVIYSKHFWSGQDRSSSADKRKYGDPDAFRPAP"
    "GTGLVDMSRDRNIPRSPTSPGEGFVNFDYGWFGAQTEADADKTVWTHGNHYHAPNGSLGAMHVYESKFRNWSEGY"
    "SDFDRGAYVITFIPKSWNTAPDKVKQGWP"
)
P81453_MATURE_SEQUENCE = (
    "DSDDRVTPPAEPLDRMPDPYRPSYGRAETVVNNYIRKWQQVYSHRDGRKQQMTEEQREWLSYGCVGVTWVNSGQYP"
    "TNRLAFASFDEDRFKNELKNGRPRSGETRAEFEGRVAKESFDEEKGFQRAREVASVMNRALENAHDESAYLDNLKK"
    "ELANGNDALRNEDARSPFYSALRNTPSFKERNGGNHDPSRMKAVIYSKHFWSGQDRSSSADKRKYGDPDAFRPAP"
    "GTGLVDMSRDRNIPRSPTSPGEGFVNFDYGWFGAQTEADADKTVWTHGNHYHAPNGSLGAMHVYESKFRNWSEGY"
    "SDFDRGAYVITFIPKSWNTAPDKVKQGWP"
)
MOCK_MTGASE_SEQUENCE = P81453_MATURE_SEQUENCE
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
    mature_sequence: str | None = None
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
        is_aqgt = "AQGT" in accession.upper()
        sequence = MOCK_AQGT_SEQUENCE if is_aqgt else P81453_FULL_SEQUENCE
        mature_sequence = None if is_aqgt else P81453_MATURE_SEQUENCE
        protein_name = (
            "Mock anthraquinone glycosyltransferase"
            if is_aqgt
            else "Mock microbial transglutaminase"
        )
        ec_number = None if is_aqgt else "2.3.2.13"
        return UniProtEntry(
            accession=accession,
            protein_name=protein_name,
            organism="Streptomyces mobaraensis",
            ec_number=ec_number,
            sequence=sequence,
            mature_sequence=mature_sequence,
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


def _first_ec_number(description: dict) -> str | None:
    recommended = description.get("recommendedName") or {}
    ec_numbers = recommended.get("ecNumbers") or []
    if ec_numbers and isinstance(ec_numbers[0], dict):
        return ec_numbers[0].get("value")
    return None


def _protein_name(description: dict) -> str:
    recommended = description.get("recommendedName") or {}
    full_name = recommended.get("fullName") or {}
    return full_name.get("value") or "Unknown UniProt protein"


def parse_uniprot_entry_payload(payload: dict) -> UniProtEntry:
    cross_references = {}
    for item in payload.get("uniProtKBCrossReferences", []):
        if not item.get("database") or not item.get("id"):
            continue
        cross_references.setdefault(str(item.get("database")), str(item.get("id")))
    description = payload.get("proteinDescription") or {}
    sequence = (payload.get("sequence") or {}).get("value")
    return UniProtEntry(
        accession=str(payload.get("primaryAccession") or ""),
        protein_name=_protein_name(description),
        organism=(payload.get("organism") or {}).get("scientificName"),
        ec_number=_first_ec_number(description),
        sequence=sequence,
        mature_sequence=_mature_sequence_from_features(sequence, payload.get("features") or []),
        cross_references=cross_references,
    )


def _mature_sequence_from_features(sequence: str | None, features: list[dict]) -> str | None:
    if not sequence:
        return None
    for feature in features:
        if feature.get("type") != "Chain":
            continue
        location = feature.get("location") or {}
        start = (location.get("start") or {}).get("value")
        end = (location.get("end") or {}).get("value")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start < 1 or end < start or end > len(sequence):
            continue
        return sequence[start - 1 : end]
    return None


def parse_uniprot_search_hits(payload: dict) -> list[UniProtSearchHit]:
    hits = []
    for item in payload.get("results", []):
        entry = parse_uniprot_entry_payload(item)
        hits.append(
            UniProtSearchHit(
                accession=entry.accession,
                protein_name=entry.protein_name,
                organism=entry.organism,
                ec_number=entry.ec_number,
                score=item.get("score"),
            )
        )
    return hits


class RealUniProtClient:
    source = "uniprot"
    base_url = "https://rest.uniprot.org"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def search_by_keyword(self, keyword: str, size: int = 5) -> list[UniProtSearchHit]:
        params = {"query": keyword, "format": "json", "size": size}
        response = httpx.get(f"{self.base_url}/uniprotkb/search", params=params, timeout=self.timeout)
        response.raise_for_status()
        return parse_uniprot_search_hits(response.json())[:size]

    def search_by_ec(self, ec_number: str, size: int = 5) -> list[UniProtSearchHit]:
        return self.search_by_keyword(f"ec:{ec_number}", size=size)

    def search_by_organism(self, organism: str, size: int = 5) -> list[UniProtSearchHit]:
        return self.search_by_keyword(f"organism_name:{organism}", size=size)

    def fetch_entry(self, accession: str) -> UniProtEntry:
        response = httpx.get(f"{self.base_url}/uniprotkb/{accession}.json", timeout=self.timeout)
        response.raise_for_status()
        entry = parse_uniprot_entry_payload(response.json())
        entry.cross_references["provenance"] = build_real_provenance(
            provider="uniprot",
            source_url=f"{self.base_url}/uniprotkb/{accession}.json",
        )
        return entry

    def fetch_fasta(self, accession: str) -> str:
        response = httpx.get(f"{self.base_url}/uniprotkb/{accession}.fasta", timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def fetch_cross_references(self, accession: str) -> dict[str, str]:
        return self.fetch_entry(accession).cross_references


def get_uniprot_client() -> MockUniProtClient | RealUniProtClient:
    if get_settings().use_real_science_providers:
        return RealUniProtClient()
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
