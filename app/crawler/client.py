import httpx


class WebClient:

    def __init__(self):

        self.client = httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
        )

    async def fetch(self, url: str):

        response = await self.client.get(url)

        response.raise_for_status()

        return response.text
