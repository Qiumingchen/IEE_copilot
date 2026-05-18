import httpx


class AlphaFoldClient:
    base_url = "https://alphafold.ebi.ac.uk/api"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def fetch_prediction(self, uniprot_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/prediction/{uniprot_id}")
            response.raise_for_status()
            return response.json()
