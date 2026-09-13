from urllib.parse import (
    urljoin,
    urlparse,
)

from bs4 import BeautifulSoup


class LinkDiscovery:

    def discover(
        self,
        html: str,
        current_url: str,
        domain: str,
    ):

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        urls = set()

        for anchor in soup.find_all(
            "a",
            href=True,
        ):

            url = urljoin(
                current_url,
                anchor["href"],
            )

            parsed = urlparse(url)

            if parsed.netloc == domain:

                clean_url = (
                    parsed._replace(
                        fragment=""
                    ).geturl()
                )

                urls.add(clean_url)

        return urls
