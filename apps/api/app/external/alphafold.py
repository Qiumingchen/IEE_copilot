from dataclasses import dataclass, field

import httpx


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


def get_alphafold_client() -> MockAlphaFoldClient:
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
