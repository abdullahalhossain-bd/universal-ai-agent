from bs4 import BeautifulSoup


class HTMLExtractor:

    def extract(
        self,
        html: str,
    ):

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg",
        ]):

            tag.decompose()

        title = None

        if soup.title:

            title = soup.title.get_text(
                " ",
                strip=True,
            )

        text = soup.get_text(
            "\n",
            strip=True,
        )

        return {
            "title": title,
            "content": text,
        }
