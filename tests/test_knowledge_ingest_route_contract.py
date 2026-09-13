from app.api.v1.knowledge import WebsiteIngestRequest
from app.main import app


def test_knowledge_ingest_has_single_canonical_route():
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/v1/knowledge/ingest"
        and "POST" in (getattr(route, "methods", None) or set())
    ]
    assert len(routes) == 1
    assert routes[0].endpoint.__module__ == "app.api.v1.knowledge"


def test_dashboard_website_payload_matches_canonical_ingest_contract():
    payload = WebsiteIngestRequest.model_validate({"website_url": "https://example.com"})
    assert payload.website_url == "https://example.com"


def test_dashboard_website_payload_without_url_is_rejected():
    import pytest

    with pytest.raises(Exception):
        WebsiteIngestRequest.model_validate({})
