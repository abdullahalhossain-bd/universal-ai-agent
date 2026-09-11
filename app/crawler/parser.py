from __future__ import annotations

import json
from bs4 import BeautifulSoup


def _json_value(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value
    return None


def extract_structured_data(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        values = parsed if isinstance(parsed, list) else [parsed]
        for value in values:
            if isinstance(value, dict) and isinstance(value.get("@graph"), list):
                values.extend(x for x in value["@graph"] if isinstance(x, dict))
            elif isinstance(value, dict):
                items.append(value)
    return items


def extract_text(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def extract_metadata(html: str):
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    description_tag = soup.find("meta", attrs={"name": "description"})
    description = description_tag.get("content") if description_tag else None
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])]
    return {"title": title, "description": description, "headings": headings}


def parse_page(html: str) -> dict:
    metadata = extract_metadata(html)
    return {
        **metadata,
        "content": extract_text(html),
        "structured_data": extract_structured_data(html),
    }
