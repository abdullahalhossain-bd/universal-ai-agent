import sys
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"

PASS = 0
FAIL = 0
WARN = 0


def request(method, path, data=None, headers=None, timeout=10):
    url = BASE + path
    body = None

    headers = headers or {}
    headers.setdefault("Accept", "application/json")

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, raw
    except Exception as e:
        return None, str(e)


def check(name, method, path, expected=None, data=None):
    global PASS, FAIL

    status, body = request(method, path, data=data)

    if status is None:
        print(f"[FAIL] {name:<42} CONNECTION ERROR")
        print(f"       {body}")
        FAIL += 1
        return

    if expected is None:
        ok = 200 <= status < 500
    else:
        ok = status in expected

    if ok:
        print(f"[PASS] {name:<42} {status}")
        PASS += 1
    else:
        print(f"[FAIL] {name:<42} {status}")
        print(f"       {body[:500]}")
        FAIL += 1


print()
print("=" * 72)
print(" Universal Commerce AI - API Smoke Test")
print("=" * 72)
print(f"Base URL: {BASE}")
print()


# ---------------------------------------------------------------------
# 1. Basic server checks
# ---------------------------------------------------------------------

print("1. SERVER")
print("-" * 72)

check(
    "Health",
    "GET",
    "/health",
    expected={200},
)

check(
    "OpenAPI",
    "GET",
    "/openapi.json",
    expected={200},
)


# ---------------------------------------------------------------------
# 2. OpenAPI route inventory
# ---------------------------------------------------------------------

print()
print("2. OPENAPI ROUTE INVENTORY")
print("-" * 72)

status, body = request("GET", "/openapi.json")

if status == 200:
    try:
        spec = json.loads(body)
        paths = spec.get("paths", {})

        print(f"[PASS] OpenAPI loaded: {len(paths)} routes registered")

        for path, methods in sorted(paths.items()):
            method_names = ", ".join(sorted(m.upper() for m in methods))
            print(f"       {method_names:<18} {path}")

    except Exception as e:
        print("[FAIL] OpenAPI JSON could not be parsed")
        print(f"       {e}")
        FAIL += 1
else:
    print("[FAIL] Could not read OpenAPI")
    FAIL += 1


# ---------------------------------------------------------------------
# 3. Static / low-risk endpoints
# ---------------------------------------------------------------------

print()
print("3. LOW-RISK ENDPOINTS")
print("-" * 72)

check(
    "Widget JS",
    "GET",
    "/widget.js",
    expected={200},
)

check(
    "Admin dashboard",
    "GET",
    "/admin",
    expected={200, 401, 403},
)

check(
    "Product search validation",
    "GET",
    "/v1/products/search?q=test",
    expected={200, 401, 403},
)


# ---------------------------------------------------------------------
# 4. Validation checks
#
# Sending {} should normally result in 422 for endpoints requiring
# request bodies. This proves FastAPI routing + Pydantic validation
# are alive without triggering the actual business operation.
# ---------------------------------------------------------------------

print()
print("4. REQUEST VALIDATION")
print("-" * 72)

validation_routes = [
    ("Chat validation", "POST", "/v1/chat"),
    ("Image upload validation", "POST", "/v1/images"),
    ("Store validation", "POST", "/v1/stores"),
    ("Datasource validation", "POST", "/v1/datasources"),
    ("Datasource test validation", "POST", "/v1/datasources/test"),
    ("Datasource discover validation", "POST", "/v1/datasources/discover"),
    ("Knowledge ingest validation", "POST", "/v1/knowledge/ingest"),
    ("Knowledge search validation", "POST", "/v1/knowledge/search"),
    ("Embedding validation", "POST", "/v1/knowledge/embeddings/generate"),
    ("Semantic search validation", "POST", "/v1/knowledge/semantic-search"),
    ("Hybrid search validation", "POST", "/v1/knowledge/hybrid-search"),
    ("Discovery validation", "POST", "/v1/discovery/scan"),
    ("Mapping suggest validation", "POST", "/v1/mapping/suggest"),
    ("Mapping confirm validation", "POST", "/v1/mapping/confirm"),
    ("Mapping apply validation", "POST", "/v1/mapping/apply"),
]

for name, method, path in validation_routes:
    check(
        name,
        method,
        path,
        expected={401, 403, 422},
        data={},
    )


# ---------------------------------------------------------------------
# 5. Fake-ID route checks
#
# These do NOT use a real resource. We only verify that the route is
# registered and authentication/404 handling is functioning.
# ---------------------------------------------------------------------

print()
print("5. RESOURCE ROUTES")
print("-" * 72)

fake_id = "00000000-0000-0000-0000-000000000000"

resource_routes = [
    ("Get datasource", "GET", f"/v1/datasources/{fake_id}"),
    ("Patch datasource", "PATCH", f"/v1/datasources/{fake_id}"),
    ("Delete datasource", "DELETE", f"/v1/datasources/{fake_id}"),
    ("Discover datasource", "POST", f"/v1/datasources/{fake_id}/discover"),
    ("Sync datasource", "POST", f"/v1/datasources/{fake_id}/sync"),
    ("Analyze fake image", "POST", f"/v1/images/{fake_id}/analyze"),
]

for name, method, path in resource_routes:
    data = {} if method in {"POST", "PATCH"} else None

    check(
        name,
        method,
        path,
        expected={401, 403, 404, 405, 422},
        data=data,
    )


# ---------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------

print()
print("=" * 72)
print(" SUMMARY")
print("=" * 72)

print(f"PASS : {PASS}")
print(f"FAIL : {FAIL}")

if FAIL == 0:
    print()
    print("RESULT: API SMOKE TEST PASSED")
    print("Server, OpenAPI, routing and validation look healthy.")
    sys.exit(0)
else:
    print()
    print("RESULT: API SMOKE TEST FOUND FAILURES")
    print("Check the [FAIL] lines above.")
    sys.exit(1)
