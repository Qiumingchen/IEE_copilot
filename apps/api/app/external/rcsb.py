import httpx


class RcsbClient:
    base_url = "https://data.rcsb.org/rest/v1/core"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def fetch_entry(self, pdb_id: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/entry/{pdb_id.lower()}")
            response.raise_for_status()
            return response.json()
