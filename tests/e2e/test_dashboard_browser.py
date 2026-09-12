import subprocess
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend-dashboard"
BASE_URL = "http://127.0.0.1:4173"


def test_dashboard_login_and_protected_route():
    process = subprocess.Popen(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "4173", "--strictPort"],
        cwd=FRONTEND,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                import urllib.request
                urllib.request.urlopen(BASE_URL + "/login", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("Vite dev server did not start")

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            def mock_api(route):
                path = route.request.url.split(BASE_URL, 1)[-1]
                if path == "/v1/auth/me":
                    return route.fulfill(status=401, content_type="application/json", body='{"detail":"Not authenticated"}')
                if path == "/v1/auth/login":
                    return route.fulfill(
                        status=200,
                        content_type="application/json",
                        body='{"access_token":"e2e-token","user":{"id":"user-1","email":"merchant@example.com"},"store":{"id":"store-1","name":"E2E Store"}}',
                    )
                if path == "/v1/auth/inbox/establish":
                    return route.fulfill(status=200, content_type="application/json", body='{"ok":true}')
                if path == "/v1/auth/logout":
                    return route.fulfill(status=200, content_type="application/json", body='{"ok":true}')
                return route.fulfill(status=404, content_type="application/json", body='{"detail":"not mocked"}')

            page.route("**/v1/**", mock_api)
            page.goto(BASE_URL + "/login")
            expect(page.get_by_role("heading", name="Welcome back")).to_be_visible()
            page.get_by_label("Email").fill("merchant@example.com")
            page.get_by_label("Password").fill("password123")
            page.get_by_role("button", name="Log in").click()
            page.wait_for_url(BASE_URL + "/")
            expect(page).to_have_url(BASE_URL + "/")
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
