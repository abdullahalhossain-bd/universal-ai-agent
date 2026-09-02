from bs4 import BeautifulSoup


def extract_text(html: str):

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    for tag in soup([
        "script",
        "style",
        "noscript",
        "nav",
        "footer",
    ]):

        tag.decompose()

    return soup.get_text(
        separator=" ",
        strip=True,
    )


def extract_metadata(html: str):

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    title_tag = soup.find("title")

    title = (
        title_tag.get_text(strip=True)
        if title_tag
        else None
    )

    description_tag = soup.find(
        "meta",
        attrs={"name": "description"},
    )

    description = (
        description_tag.get("content")
        if description_tag
        else None
    )

    headings = [
        h.get_text(strip=True)
        for h in soup.find_all(
            ["h1", "h2", "h3"]
        )
    ]

    return {
        "title": title,
        "description": description,
        "headings": headings,
    }
