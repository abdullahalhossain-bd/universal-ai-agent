import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "http://127.0.0.1:8765"
API_KEY = "test-public-key-12345678"
TOKEN = "conversation-token-e2e"
CONVERSATION = "conversation-e2e"


@pytest.fixture(scope="module")
def static_server():
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8765", "--bind", "127.0.0.1"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                import urllib.request

                urllib.request.urlopen(BASE_URL + "/tests/e2e/widget_harness.html", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("Static test server did not start")
        yield
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_widget_chat_live_support_and_image_flow(static_server):
    seen = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        def handle_api(route):
            request = route.request
            seen.append((request.method, request.url, dict(request.headers)))
            path = request.url.split(BASE_URL, 1)[-1]

            if request.method == "POST" and path == "/v1/chat":
                return route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"message":"Laptop found","conversation_id":"conversation-e2e","conversation_token":"conversation-token-e2e","products":[]}',
                )

            if request.method == "GET" and path.startswith("/v1/messages/customer/conversation-e2e"):
                return route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"conversation_id":"conversation-e2e","mode":"ai","mode_owner":"ai","messages":[]}',
                )

            if request.method == "POST" and path == "/v1/messages/customer/conversation-e2e/mode":
                assert request.headers.get("x-conversation-token") == TOKEN
                return route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"conversation_id":"conversation-e2e","mode":"human","mode_owner":"customer"}',
                )

            if request.method == "POST" and path == "/v1/messages/customer/conversation-e2e":
                assert request.headers.get("x-conversation-token") == TOKEN
                return route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"id":"merchant-user-1","role":"user","content":"hello merchant"}',
                )

            if request.method == "POST" and path == "/v1/images":
                assert request.headers.get("x-api-key") == API_KEY
                assert request.headers.get("x-conversation-token") == TOKEN
                return route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"image_id":"image-e2e","url":"https://example.com/test.png","mime_type":"image/png","size":68}',
                )

            if request.method == "POST" and path == "/v1/images/image-e2e/analyze":
                assert request.headers.get("x-conversation-token") == TOKEN
                return route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"message":"Image analyzed","conversation_id":"conversation-e2e","conversation_token":"conversation-token-e2e","products":[]}',
                )

            return route.fulfill(status=404, content_type="application/json", body='{"detail":"not mocked"}')

        page.route("**/v1/**", handle_api)
        page.goto(BASE_URL + "/tests/e2e/widget_harness.html")

        host = page.locator("body > div").last
        bubble = host.locator("button.bubble")
        expect(bubble).to_be_visible()
        bubble.click()

        panel = host.locator(".panel")
        expect(panel).to_be_visible()
        expect(host.locator(".merchant-chat-button")).to_have_count(0)

        input_box = host.locator("textarea.input")
        input_box.fill("laptop")
        host.locator("button.send").click()
        expect(host.locator(".assistant").last).to_contain_text("Laptop found")

        host.locator("button.mode-btn.live").click()
        expect(host.locator(".mode-label")).to_contain_text("Live merchant")

        input_box.fill("hello merchant")
        host.locator("button.send").click()
        expect(host.locator(".user").last).to_contain_text("hello merchant")

        image_input = host.locator("input.image-input")
        image_input.set_input_files(
            {"name": "test.png", "mimeType": "image/png", "buffer": b"\x89PNG\r\n\x1a\n" + b"0" * 60}
        )
        expect(host.locator(".assistant").last).to_contain_text("Image analyzed")

        image_uploads = [entry for entry in seen if entry[1].endswith("/v1/images")]
        assert image_uploads, "image upload request was not made"
        assert image_uploads[-1][2].get("x-conversation-token") == TOKEN

        browser.close()
