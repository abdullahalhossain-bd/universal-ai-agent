import httpx

from app.knowledge.crawler import (
    assert_safe_url,
)


class PageFetcher:

    def __init__(self):

        # NOTE: currently unused by the active knowledge
        # ingestion path (KnowledgeService uses WebsiteCrawler).
        # Kept safe regardless: redirects are NOT auto-followed
        # and every request is SSRF-validated first.
        self.client = httpx.AsyncClient(
            timeout=10,
            follow_redirects=False,
            headers={
                "User-Agent":
                "EcommerceAI-Bot/1.0"
            },
        )

    async def fetch(
        self,
        url: str,
    ):

        await assert_safe_url(url)

        response = await self.client.get(
            url
        )

        if response.is_redirect:
            raise ValueError(
                "Refusing to follow redirect; "
                "use WebsiteCrawler instead"
            )

        response.raise_for_status()

        content_type = (
            response.headers
            .get("content-type", "")
            .lower()
        )

        if "text/html" not in content_type:

            return None

        return response.text

    async def close(self):

        await self.client.aclose()
