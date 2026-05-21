from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class AlphaFoldModelMetadata:
    model_id: str
    uniprot_id: str
    structure_url: str
    confidence_url: str
    confidence_summary: dict = field(default_factory=dict)


class MockAlphaFoldClient:
    source = "alphafold_mock"

    def fetch_model_by_uniprot(self, uniprot_id: str) -> AlphaFoldModelMetadata:
        normalized = uniprot_id.upper()
        model_id = f"AF-{normalized}-F1"
        return AlphaFoldModelMetadata(
            model_id=model_id,
            uniprot_id=normalized,
            structure_url=f"mock://alphafold/{model_id}.pdb",
            confidence_url=f"mock://alphafold/{model_id}.json",
            confidence_summary={
                "mean_plddt": 90.0,
                "confidence_version": "mock-v1",
            },
        )

    def download_predicted_structure(self, model_id: str) -> str:
        return f"HEADER    MOCK ALPHAFOLD MODEL {model_id}\nATOM      1  CA  ALA A   1\nEND\n"

    def store_confidence_metadata(self, model_id: str) -> dict:
        return {
            "model_id": model_id,
            "mean_plddt": 90.0,
            "confidence_version": "mock-v1",
        }


def parse_alphafold_prediction(payload: list[dict]) -> AlphaFoldModelMetadata:
    if not payload:
        raise ValueError("AlphaFold prediction response is empty")
    item = payload[0]
    return AlphaFoldModelMetadata(
        model_id=str(item.get("entryId") or ""),
        uniprot_id=str(item.get("uniprotAccession") or ""),
        structure_url=str(item.get("pdbUrl") or item.get("cifUrl") or ""),
        confidence_url=str(item.get("paeDocUrl") or ""),
        confidence_summary={"mean_plddt": item.get("confidenceScore")},
    )


class RealAlphaFoldClient:
    source = "alphafold"
    base_url = "https://alphafold.ebi.ac.uk/api"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def fetch_model_by_uniprot(self, uniprot_id: str) -> AlphaFoldModelMetadata:
        response = httpx.get(f"{self.base_url}/prediction/{uniprot_id}", timeout=self.timeout)
        response.raise_for_status()
        return parse_alphafold_prediction(response.json())

    def download_predicted_structure(self, model_id: str) -> str:
        response = httpx.get(f"https://alphafold.ebi.ac.uk/files/{model_id}-model_v4.pdb", timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def store_confidence_metadata(self, model_id: str) -> dict:
        return {"model_id": model_id, "confidence_source": "alphafold"}


def get_alphafold_client() -> MockAlphaFoldClient | RealAlphaFoldClient:
    if get_settings().use_real_science_providers:
        return RealAlphaFoldClient()
    return MockAlphaFoldClient()


class AlphaFoldClient:
    base_url = "https://alphafold.ebi.ac.uk/api"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def fetch_prediction(self, uniprot_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/prediction/{uniprot_id}")
            response.raise_for_status()
            return response.json()
