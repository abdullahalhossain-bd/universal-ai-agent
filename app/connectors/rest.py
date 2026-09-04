from typing import Any
from urllib.parse import quote

import httpx

from app.connectors.base.connector import Connector
from app.core.network_guard import assert_safe_http_url
from app.schemas.product import UniversalProduct
from app.discovery.models import ColumnInfo, DatabaseSchema, TableInfo


class RESTConnector(Connector):

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        options: dict | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.options = options or {}
        assert_safe_http_url(self.base_url)

    def _endpoint(self, name: str, default: str) -> str:
        value = self.options.get(name, default)
        if not isinstance(value, str) or not value.startswith("/"):
            raise ValueError(f"REST option {name} must be an absolute path")
        url = f"{self.base_url}{value}"
        assert_safe_http_url(url)
        return url

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.get(self.base_url, headers=self._headers())
                return response.status_code < 400
        except Exception:
            return False

    async def discover(self):
        payload = await self._request_json(
            "GET", self._endpoint("schema_endpoint", "/schema")
        )
        tables = []
        for table in payload.get("tables", []):
            tables.append(
                TableInfo(
                    name=str(table["name"]),
                    columns=[
                        ColumnInfo(
                            name=str(column["name"]),
                            data_type=str(column.get("data_type", "unknown")),
                            nullable=bool(column.get("nullable", True)),
                        )
                        for column in table.get("columns", [])
                    ],
                )
            )
        return DatabaseSchema(tables=tables)

    async def get_products(self, limit: int = 50, offset: int = 0) -> list[UniversalProduct]:
        payload = await self._request_json(
            "GET",
            self._endpoint("products_endpoint", "/products"),
            params={"limit": limit, "offset": offset},
        )
        rows = payload.get("products", payload) if isinstance(payload, dict) else payload
        return [self._normalize_product(row) for row in rows]

    async def get_product(self, product_id: str) -> UniversalProduct | None:
        try:
            payload = await self._request_json(
                "GET",
                self._endpoint("product_endpoint", "/products") + f"/{quote(str(product_id), safe='')}",
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return self._normalize_product(payload)

    async def get_inventory(self, product_id: str) -> dict[str, Any]:
        return await self._request_json(
            "GET",
            self._endpoint("inventory_endpoint", "/products") + f"/{quote(str(product_id), safe='')}/inventory",
        )

    async def get_store_info(self) -> dict[str, Any]:
        return await self._request_json("GET", self._endpoint("store_endpoint", "/store"))

    def fetch_product_rows(
        self,
        table_name: str,
        columns: list[str],
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Synchronous paginated row fetch used by the generic sync service.

        REST APIs expose product objects rather than SQL rows, so table_name
        and columns are compatibility parameters. The endpoint returns the
        merchant's product objects and the existing mapping/normalizer handles
        the selected fields.
        """
        _ = table_name, columns
        url = self._endpoint("products_endpoint", "/products")
        assert_safe_http_url(url)
        with httpx.Client(
            timeout=httpx.Timeout(10.0, connect=3.0),
            follow_redirects=False,
        ) as client:
            response = client.get(
                url,
                headers=self._headers(),
                params={"limit": limit, "offset": offset},
            )
            response.raise_for_status()
            payload = response.json()

        rows = payload.get("products", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("REST products endpoint must return a list or an object with a 'products' list")
        return [row for row in rows if isinstance(row, dict)]

    async def _request_json(self, method: str, url: str, **kwargs) -> Any:
        assert_safe_http_url(url)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=3.0),
            follow_redirects=False,
        ) as client:
            response = await client.request(method, url, headers=self._headers(), **kwargs)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _normalize_product(row: dict[str, Any]) -> UniversalProduct:
        return UniversalProduct(
            id=str(row.get("id", row.get("product_id", ""))),
            name=str(row.get("name", row.get("product_name", ""))),
            description=row.get("description"),
            price=row.get("price", row.get("selling_price")),
            currency=row.get("currency"),
            stock=row.get("stock", row.get("quantity")),
            sku=row.get("sku"),
            category=row.get("category"),
            brand=row.get("brand"),
            url=row.get("url", row.get("product_url")),
            source_metadata=dict(row),
        )
