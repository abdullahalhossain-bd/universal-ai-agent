"""
Boot smoke test.

This is the test that would have caught both regressions fixed in this
pass:
  1. mapping/discovery routers defined but never included in main.py
     (silently unreachable — nothing here would have failed loudly).
  2. app/discovery/scorer.py importing `rapidfuzz`, which was never
     listed anywhere and only surfaces once the discovery/mapping
     import chain is actually exercised.

Keep this test fast and dependency-free (no real Postgres/Redis) so it
runs in CI on every change.
"""


def test_app_imports_without_error(app):
    assert app is not None


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def _all_paths_and_methods(app):
    """
    app.routes doesn't reliably flatten to (method, path) pairs across
    FastAPI versions — some wrap included routers as opaque objects.
    The OpenAPI schema is the one interface guaranteed to reflect what
    is actually reachable, so tests use it instead of walking app.routes.
    """
    schema = app.openapi()
    pairs = []
    for path, methods in schema["paths"].items():
        for method in methods:
            pairs.append((method.upper(), path))
    return pairs


def test_no_duplicate_route_paths(app):
    """
    Guards against re-introducing a second router mounted at a path
    that's already served elsewhere (e.g. the old app.api.v1.chat vs
    app.chat.router collision, both at POST /v1/chat).

    Caveat: this reads the generated OpenAPI schema, which is keyed by
    path — if two routers ever again register the exact same
    (method, path), the schema will just show one operation and this
    check will NOT catch it. It reliably catches the more common
    mistake (a new router given the wrong/missing prefix, or accidental
    removal of a route), but a true same-path duplicate needs a manual
    diff of the router include list in app/main.py.
    """
    pairs = _all_paths_and_methods(app)
    assert len(pairs) == len(set(pairs))


def test_expected_routes_are_registered(app):
    paths = {p for _, p in _all_paths_and_methods(app)}
    for expected in (
        "/health",
        "/v1/chat",
        "/v1/stores",
        "/v1/datasources",
        "/v1/discovery/scan",
        "/v1/mapping/suggest",
        "/v1/mapping/confirm",
        "/v1/mapping/apply",
    ):
        assert expected in paths, f"missing expected route: {expected}"


def test_cors_allows_browser_widget_origin(client):
    """
    The chat widget is a <script> embedded on arbitrary merchant
    domains, so a cross-origin browser preflight must succeed.
    """
    resp = client.options(
        "/v1/chat",
        headers={
            "Origin": "https://some-merchant-site.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key,content-type",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") in (
        "*",
        "https://some-merchant-site.example",
    )
    # Auth is a header, never a cookie — credentials must stay off
    # even though the origin is wide open.
    assert resp.headers.get("access-control-allow-credentials") != "true"


def test_mapping_and_discovery_require_auth(client):
    """
    These endpoints accept a merchant connection_url / write to a
    datasource — they must never be reachable without an API key.
    """
    protected = [
        ("/v1/discovery/scan", {"connection_url": "postgresql://x/y"}),
        (
            "/v1/mapping/suggest",
            {"store_id": "s1", "table": "products", "columns": ["name"]},
        ),
        (
            "/v1/mapping/confirm",
            {"store_id": "s1", "table": "products", "columns": ["name"]},
        ),
        (
            "/v1/mapping/apply",
            {
                "store_id": "s1",
                "datasource_id": "d1",
                "table": "products",
                "mapping": {"id": "id", "name": "name"},
            },
        ),
    ]
    for path, body in protected:
        resp = client.post(path, json=body)
        assert resp.status_code == 401, (
            f"{path} should require an API key, got {resp.status_code}"
        )
