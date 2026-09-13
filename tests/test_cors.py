"""
Regression test for the CORS `allow_headers` allow-list.

`x-conversation-token` is required by several customer-facing endpoints
(`/v1/messages/customer/*`, `/v1/images`) whenever a conversation already
has an access token. Those endpoints are meant to be called cross-origin
from the merchant's own website via the embedded widget, so the header
must be preflight-approved or the browser blocks the real request before
it is ever sent — the request never reaches the backend at all, so no
server-side test of the endpoint itself would ever catch this.
"""


def test_cors_preflight_allows_conversation_token_header(client):
    response = client.options(
        "/v1/messages/customer/some-conversation-id",
        headers={
            "Origin": "https://merchant-storefront.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key, content-type, x-conversation-token",
        },
    )

    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-conversation-token" in allowed, (
        "x-conversation-token must be in the CORS allow_headers list — "
        "without it, browsers block every cross-origin request that "
        "carries this header before it reaches the backend at all "
        "(customer messaging, mode switching, and image upload all use it)."
    )
