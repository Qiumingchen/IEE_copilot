import httpx


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
