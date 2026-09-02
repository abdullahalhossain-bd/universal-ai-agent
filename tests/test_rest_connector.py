import pytest
import httpx

from app.connectors.rest import RESTConnector


@pytest.fixture
def connector():
    return RESTConnector(
        "https://example.com",
        api_key="test-token",
        options={
            "schema_endpoint": "/schema",
            "products_endpoint": "/products",
            "product_endpoint": "/products",
            "inventory_endpoint": "/inventory",
            "store_endpoint": "/store",
        },
    )


@pytest.fixture
def mock_http(monkeypatch):
    requests = []
    real_client = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        if request.url.path == "/schema":
            return httpx.Response(
                200,
                json={"tables": [{"name": "products", "columns": [{"name": "id"}]}]},
            )
        if request.url.path == "/products":
            return httpx.Response(
                200,
                json={"products": [{"id": "sku/1", "name": "Widget", "price": 3.5}]},
            )
        if request.url.path in {"/products/sku%2F1", "/products/sku/1"}:
            return httpx.Response(200, json={"id": "sku/1", "name": "Widget"})
        if request.url.path in {
            "/inventory/sku%2F1/inventory",
            "/inventory/sku/1/inventory",
        }:
            return httpx.Response(200, json={"stock": 4})
        return httpx.Response(200, json={"name": "Merchant"})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )
    return requests


@pytest.mark.asyncio
async def test_rest_connector_contract(connector, mock_http):
    schema = await connector.discover()
    products = await connector.get_products(limit=1, offset=2)
    product = await connector.get_product("sku/1")
    inventory = await connector.get_inventory("sku/1")
    store = await connector.get_store_info()

    assert schema.tables[0].name == "products"
    assert products[0].id == "sku/1"
    assert product.name == "Widget"
    assert inventory == {"stock": 4}
    assert store == {"name": "Merchant"}
    assert all(request.headers["Authorization"] == "Bearer test-token" for request in mock_http)
    assert any(request.url.params["offset"] == "2" for request in mock_http if request.url.path == "/products")


def test_rest_connector_rejects_private_or_credential_urls(monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_DATASOURCE_HOSTS", raising=False)
    with pytest.raises(ValueError):
        RESTConnector("http://127.0.0.1:8080")
    with pytest.raises(ValueError):
        RESTConnector("https://user:pass@merchant.example")
