import pytest

from app.crawler.classifier import classify_page
from app.crawler.parser import extract_structured_data
from app.crawler.web_ingestion import extract_products_from_structured_data


def test_json_ld_product_is_discovered_without_fixed_field_names():
    html = '''<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Dynamic Phone","sku":"P-1","image":"https://example.test/p.jpg","offers":{"price":"99.5","priceCurrency":"USD"}}</script>'''
    data = extract_structured_data(html)
    rows = extract_products_from_structured_data(data, "https://example.test/products/p-1")
    assert rows[0]["name"] == "Dynamic Phone"
    assert rows[0]["price"] == "99.5"
    assert rows[0]["currency"] == "USD"
    assert rows[0]["product_url"].endswith("/products/p-1")


def test_graph_and_embedded_json_are_discovered():
    html = '''<script type="application/json">{"state":{"product":{"@type":"Product","name":"Embedded Item","offers":{"price":10}}}}</script>'''
    data = extract_structured_data(html)
    assert any(x.get("name") == "Embedded Item" for x in data)


def test_semantic_microdata_product_is_discovered():
    html = '''<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Micro Item</span><meta itemprop="sku" content="M-1"><div itemprop="offers" itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" content="25"><meta itemprop="priceCurrency" content="USD"></div></div>'''
    data = extract_structured_data(html)
    assert any(x.get("name") == "Micro Item" for x in data)


def test_classifier_uses_content_before_url_hints():
    assert classify_page("https://merchant.test/x/abc", "", "Frequently Asked Questions") == "faq"
    assert classify_page("https://merchant.test/random", "Product page", "", [{"@type":"Product"}]) == "product"


def test_product_identity_is_url_stable():
    html='''<script type="application/ld+json">{"@type":"Product","name":"Same","sku":"1"}</script>'''
    data=extract_structured_data(html)
    a=extract_products_from_structured_data(data,"https://a.test/products/1")[0]["id"]
    b=extract_products_from_structured_data(data,"https://a.test/products/1")[0]["id"]
    assert a == b
    c=extract_products_from_structured_data(data,"https://a.test/products/2")[0]["id"]
    assert a != c
