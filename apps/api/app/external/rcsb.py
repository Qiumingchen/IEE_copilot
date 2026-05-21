from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class RcsbStructureMetadata:
    pdb_id: str
    title: str
    method: str | None = None
    resolution: float | None = None
    uniprot_id: str | None = None
    organism: str | None = None
    chain_summary: dict = field(default_factory=dict)
    ligand_summary: dict = field(default_factory=dict)


class MockRcsbClient:
    source = "rcsb_mock"

    def search_by_uniprot(self, uniprot_id: str, size: int = 5) -> list[str]:
        if uniprot_id.upper() in {"MOCKMTG1", "P81453"}:
            return ["1ABC"][:size]
        return []

    def search_by_keyword(self, keyword: str, size: int = 5) -> list[str]:
        lowered = keyword.lower()
        if "transglutaminase" in lowered or "mtgase" in lowered:
            return ["1ABC"][:size]
        if "anthraquinone" in lowered or "glycosyltransferase" in lowered:
            return ["2AQG"][:size]
        return []

    def fetch_structure_metadata(self, pdb_id: str) -> RcsbStructureMetadata:
        normalized = pdb_id.upper()
        if normalized == "2AQG":
            return RcsbStructureMetadata(
                pdb_id=normalized,
                title="Mock RCSB anthraquinone glycosyltransferase structure",
                method="X-RAY DIFFRACTION",
                resolution=2.2,
                uniprot_id="MOCKAQGT1",
                organism="Streptomyces mockensis",
                chain_summary={"polymer_entity_count": 1, "chains": ["A"]},
                ligand_summary={"ligands": ["AQG"]},
            )
        return RcsbStructureMetadata(
            pdb_id=normalized,
            title="Mock RCSB microbial transglutaminase structure",
            method="X-RAY DIFFRACTION",
            resolution=1.9,
            uniprot_id="MOCKMTG1",
            organism="Streptomyces mobaraensis",
            chain_summary={"polymer_entity_count": 1, "chains": ["A"]},
            ligand_summary={"ligands": ["GTP"]},
        )

    def download_pdb_or_cif(self, pdb_id: str) -> str:
        normalized = pdb_id.upper()
        return f"HEADER    MOCK RCSB STRUCTURE {normalized}\nATOM      1  CA  ALA A   1\nEND\n"


def parse_rcsb_entry_payload(payload: dict) -> RcsbStructureMetadata:
    resolution_values = (payload.get("rcsb_entry_info") or {}).get("resolution_combined") or []
    organism_rows = payload.get("rcsb_entity_source_organism") or []
    return RcsbStructureMetadata(
        pdb_id=str(payload.get("rcsb_id") or "").upper(),
        title=(payload.get("struct") or {}).get("title") or "Unknown RCSB structure",
        method=((payload.get("exptl") or [{}])[0]).get("method"),
        resolution=resolution_values[0] if resolution_values else None,
        organism=(organism_rows[0] or {}).get("scientific_name") if organism_rows else None,
        chain_summary={
            "polymer_entity_count": (payload.get("rcsb_entry_info") or {}).get(
                "polymer_entity_count_protein"
            )
        },
        ligand_summary={},
    )


class RealRcsbClient:
    source = "rcsb"
    base_url = "https://data.rcsb.org/rest/v1/core"
    search_url = "https://search.rcsb.org/rcsbsearch/v2/query"
    files_url = "https://files.rcsb.org/download"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def fetch_structure_metadata(self, pdb_id: str) -> RcsbStructureMetadata:
        response = httpx.get(f"{self.base_url}/entry/{pdb_id.lower()}", timeout=self.timeout)
        response.raise_for_status()
        return parse_rcsb_entry_payload(response.json())

    def search_by_uniprot(self, uniprot_id: str, size: int = 5) -> list[str]:
        payload = {
            "query": {
                "type": "terminal",
                "service": "text",
                "parameters": {
                    "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                    "operator": "exact_match",
                    "value": uniprot_id,
                },
            },
            "return_type": "entry",
            "request_options": {"paginate": {"start": 0, "rows": size}},
        }
        response = httpx.post(self.search_url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return [str(row["identifier"]) for row in response.json().get("result_set", [])[:size]]

    def search_by_keyword(self, keyword: str, size: int = 5) -> list[str]:
        payload = {
            "query": {
                "type": "terminal",
                "service": "full_text",
                "parameters": {"value": keyword},
            },
            "return_type": "entry",
            "request_options": {"paginate": {"start": 0, "rows": size}},
        }
        response = httpx.post(self.search_url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return [str(row["identifier"]) for row in response.json().get("result_set", [])[:size]]

    def download_pdb_or_cif(self, pdb_id: str) -> str:
        response = httpx.get(f"{self.files_url}/{pdb_id.upper()}.pdb", timeout=self.timeout)
        response.raise_for_status()
        return response.text


def get_rcsb_client() -> MockRcsbClient | RealRcsbClient:
    if get_settings().use_real_science_providers:
        return RealRcsbClient()
    return MockRcsbClient()


class RcsbClient:
    base_url = "https://data.rcsb.org/rest/v1/core"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def fetch_entry(self, pdb_id: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/entry/{pdb_id.lower()}")
            response.raise_for_status()
            return response.json()
