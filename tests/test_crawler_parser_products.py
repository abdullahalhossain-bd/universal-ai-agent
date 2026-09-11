from app.crawler.parser import extract_html_products, extract_structured_data, parse_page


def test_extracts_custom_html_without_json_ld():
    html = '''
    <html><body>
      <div class="catalog-grid">
        <div class="item product-card" data-sku="LAP-01">
          <a href="/products/alpha-laptop"><img src="/img/a.jpg"></a>
          <h3 class="product-title">Alpha Laptop</h3>
          <span class="price">৳75,000</span>
          <button>Add to Cart</button>
        </div>
      </div>
    </body></html>
    '''
    rows = extract_html_products(html, "https://merchant.example/shop")
    assert len(rows) == 1
    assert rows[0]["name"] == "Alpha Laptop"
    assert rows[0]["sku"] == "LAP-01"
    assert rows[0]["url"] == "https://merchant.example/products/alpha-laptop"
    assert rows[0]["image"] == "https://merchant.example/img/a.jpg"
    assert "75,000" in rows[0]["offers"]["price"]


def test_extracts_embedded_application_product_state():
    html = '''
    <script type="application/json">
      {"catalog":{"products":[
        {"id":"p1","name":"Blue Shirt","price":29.99,"productUrl":"/p/blue-shirt","imageUrl":"/i/blue.jpg"}
      ]}}
    </script>
    '''
    rows = extract_structured_data(html)
    assert any(row["name"] == "Blue Shirt" for row in rows)


def test_parse_page_combines_structured_and_semantic_products():
    html = '''
    <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Product","name":"Schema Phone","sku":"PH-1","offers":{"price":"499","priceCurrency":"USD"}}
    </script>
    <div class="product-card" data-product-id="2">
      <h2>Custom Camera</h2><span class="price">$299</span>
      <a href="/camera">View</a>
    </div>
    '''
    page = parse_page(html, "https://merchant.example/")
    names = {row["name"] for row in page["structured_data"]}
    assert "Schema Phone" in names
    assert "Custom Camera" in names
