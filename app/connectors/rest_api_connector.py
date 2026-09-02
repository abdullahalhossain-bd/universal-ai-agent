import httpx


class RestApiConnector:

    def __init__(
        self,
        base_url: str,
        products_endpoint: str,
        method: str = "GET",
        headers: dict | None = None,
    ):

        self.base_url = base_url
        self.products_endpoint = products_endpoint
        self.method = method
        self.headers = headers or {}

        self.client = httpx.AsyncClient(
            timeout=15,
        )

    async def test_connection(self):

        url = self.base_url + self.products_endpoint

        response = await self.client.request(
            self.method,
            url,
            headers=self.headers,
        )

        response.raise_for_status()

        return True

    async def fetch_sample(self):

        url = self.base_url + self.products_endpoint

        response = await self.client.request(
            self.method,
            url,
            headers=self.headers,
        )

        response.raise_for_status()

        return response.json()
