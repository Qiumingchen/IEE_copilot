class LiteratureClient:
    async def search_metadata(self, query: str) -> list[dict]:
        return [
            {
                "title": f"Manual literature metadata seed for {query}",
                "source": "manual_mock",
                "year": 2026,
            }
        ]
