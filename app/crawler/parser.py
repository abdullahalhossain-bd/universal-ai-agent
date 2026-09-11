from __future__ import annotations
import json
from bs4 import BeautifulSoup


def _walk_products(value):
    found=[]
    if isinstance(value,dict):
        typ=value.get("@type")
        types=typ if isinstance(typ,list) else [typ]
        if any(str(t).casefold()=="product" for t in types): found.append(value)
        for child in value.values(): found.extend(_walk_products(child))
    elif isinstance(value,list):
        for child in value: found.extend(_walk_products(child))
    return found


def extract_structured_data(html: str) -> list[dict]:
    soup=BeautifulSoup(html,"html.parser")
    items=[]
    for script in soup.find_all("script"):
        raw=script.string or script.get_text()
        if not raw or len(raw)>2_000_000: continue
        script_type=(script.get("type") or "").casefold()
        if "json" not in script_type and not raw.lstrip().startswith(("{","[")): continue
        try: parsed=json.loads(raw)
        except (TypeError,ValueError,json.JSONDecodeError): continue
        if isinstance(parsed,dict) and isinstance(parsed.get("@graph"),list): parsed=parsed["@graph"]
        items.extend(_walk_products(parsed))
    for node in soup.select('[itemtype*="Product" i]'):
        row={"@type":"Product"}
        for field in ("name","description","sku","category","brand","image","url"):
            el=node.select_one(f'[itemprop~="{field}"]')
            if not el: continue
            row[field]=el.get("content") or el.get("href") or el.get("src") or el.get_text(" ",strip=True)
        price=node.select_one('[itemprop~="price"]')
        currency=node.select_one('[itemprop~="priceCurrency"]')
        if price: row["offers"]={"price":price.get("content") or price.get_text(strip=True),"priceCurrency":currency.get("content") if currency else None}
        if row.get("name"): items.append(row)
    unique=[]; seen=set()
    for item in items:
        key=json.dumps(item,sort_keys=True,default=str)
        if key not in seen: seen.add(key); unique.append(item)
    return unique


def extract_text(html: str):
    soup=BeautifulSoup(html,"html.parser")
    for tag in soup(["script","style","noscript","nav","footer"]): tag.decompose()
    return soup.get_text(separator=" ",strip=True)


def extract_metadata(html: str):
    soup=BeautifulSoup(html,"html.parser")
    title_tag=soup.find("title")
    description_tag=soup.find("meta",attrs={"name":"description"})
    return {"title":title_tag.get_text(strip=True) if title_tag else None,"description":description_tag.get("content") if description_tag else None,"headings":[h.get_text(" ",strip=True) for h in soup.find_all(["h1","h2","h3"])]}


def parse_page(html: str) -> dict:
    metadata=extract_metadata(html)
    return {**metadata,"content":extract_text(html),"structured_data":extract_structured_data(html)}
