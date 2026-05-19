from dataclasses import dataclass, field

import httpx


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


def get_rcsb_client() -> MockRcsbClient:
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
