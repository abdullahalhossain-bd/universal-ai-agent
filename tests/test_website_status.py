from types import SimpleNamespace

import pytest

from app.api.routes import websites


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class _DB:
    def __init__(self, datasource, run):
        self.datasource = datasource
        self.run = run

    def query(self, model):
        name = getattr(model, "__name__", "")
        return _Query(self.datasource if name == "DataSource" else self.run)


class _Redis:
    async def hgetall(self, _key):
        raise ConnectionError("temporary Redis outage")

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_website_status_uses_postgres_run_when_redis_progress_fails(monkeypatch):
    datasource = SimpleNamespace(id="ds-1", store_id="store-1", connector_type="website")
    run = SimpleNamespace(
        id="run-1",
        status="success",
        started_at=None,
        finished_at=None,
        products_seen=1,
        created=1,
        updated=0,
        unchanged=0,
        quality_report={"products_found": 1},
        error=None,
    )
    store = SimpleNamespace(id="store-1")

    monkeypatch.setattr(websites, "public_datasource_dict", lambda value: {"id": value.id})
    monkeypatch.setattr(websites.redis, "from_url", lambda *args, **kwargs: _Redis())
    monkeypatch.setattr(websites, "require_feature", lambda *args, **kwargs: None)

    result = await websites.website_status("ds-1", _DB(datasource, run), store)

    assert result["crawl_progress"] is None
    assert result["last_run"]["id"] == "run-1"
    assert result["last_run"]["status"] == "success"
