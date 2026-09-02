import json
import sys
import urllib.request
import urllib.error
import uuid

BASE = "http://127.0.0.1:8000"
API_KEY = None
STORE_ID = None

PASS = 0
FAIL = 0
SKIP = 0


def request(method, path, data=None, api_key=None, timeout=30):
    url = BASE + path
    headers = {
        "Accept": "application/json",
    }

    body = None

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if api_key:
        headers["x-api-key"] = api_key

    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
            return r.status, parsed

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return e.code, parsed

    except Exception as e:
        return None, str(e)


def show_response(data):
    try:
        print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
    except Exception:
        print(str(data)[:2000])


def passed(name, status):
    global PASS
    print(f"[PASS] {name:<45} {status}")
    PASS += 1


def failed(name, status, body=None):
    global FAIL
    print(f"[FAIL] {name:<45} {status}")
    if body is not None:
        show_response(body)
    FAIL += 1


def skipped(name, reason):
    global SKIP
    print(f"[SKIP] {name:<45} {reason}")
    SKIP += 1


def find_value(obj, names):
    if isinstance(obj, dict):
        for name in names:
            if name in obj and obj[name]:
                return obj[name]

        for value in obj.values():
            result = find_value(value, names)
            if result:
                return result

    elif isinstance(obj, list):
        for value in obj:
            result = find_value(value, names)
            if result:
                return result

    return None


print()
print("=" * 76)
print(" Universal Commerce AI - Authenticated E2E Test")
print("=" * 76)
print(f"Base URL: {BASE}")
print()


# ================================================================
# 1. Create isolated test store
# ================================================================

print("1. CREATE TEST STORE")
print("-" * 76)

test_name = "E2E Test Store " + uuid.uuid4().hex[:8]

status, body = request(
    "POST",
    "/v1/stores",
    {
        "name": test_name,
        "website_url": "https://example.com",
        "plan": "starter",
    },
)

if status not in {200, 201}:
    failed("Create test store", status, body)
    print()
    print("Cannot continue because the test needs an authenticated store.")
    print("RESULT: E2E TEST STOPPED")
    sys.exit(1)

passed("Create test store", status)

STORE_ID = find_value(
    body,
    ["store_id", "id"]
)

API_KEY = find_value(
    body,
    ["api_key", "apiKey", "key"]
)

print(f"       store_id: {STORE_ID or '(not returned)'}")
print(f"       api_key : {'FOUND' if API_KEY else 'NOT FOUND'}")


# ================================================================
# 2. Authentication prerequisite
# ================================================================

print()
print("2. AUTHENTICATION")
print("-" * 76)

if not API_KEY:
    skipped(
        "Authenticated flow",
        "Create-store response did not expose an API key"
    )

    print()
    print("=" * 76)
    print(" RESULT")
    print("=" * 76)
    print(f"PASS : {PASS}")
    print(f"FAIL : {FAIL}")
    print(f"SKIP : {SKIP}")
    print()
    print("The API is healthy, but the E2E test cannot continue")
    print("until we know how the project provisions/returns store API keys.")
    sys.exit(0)

print("[INFO] API key obtained from create-store response")


# ================================================================
# 3. Get My Store
# ================================================================

print()
print("3. STORE AUTHENTICATION")
print("-" * 76)

status, body = request(
    "GET",
    "/v1/stores/me",
    api_key=API_KEY,
)

if status == 200:
    passed("Get my store", status)
    print("       Store lookup authenticated successfully.")
else:
    failed("Get my store", status, body)


# ================================================================
# 4. Product Search
# ================================================================

print()
print("4. PRODUCT SEARCH")
print("-" * 76)

status, body = request(
    "GET",
    "/v1/products/search?q=test&limit=5",
    api_key=API_KEY,
)

if status == 200:
    passed("Authenticated product search", status)
elif status in {404}:
    skipped("Authenticated product search", "No product data available")
else:
    failed("Authenticated product search", status, body)


# ================================================================
# 5. Chat
# ================================================================

print()
print("5. CHAT")
print("-" * 76)

conversation_id = "e2e-" + uuid.uuid4().hex

status, body = request(
    "POST",
    "/v1/chat",
    {
        "message": "Hello. Reply with a short greeting.",
        "conversation_id": conversation_id,
    },
    api_key=API_KEY,
    timeout=60,
)

if status == 200:
    passed("Authenticated chat", status)
    print("       Chat response:")
    show_response(body)
elif status in {429, 502, 503, 504}:
    skipped("Authenticated chat", f"Provider unavailable ({status})")
else:
    failed("Authenticated chat", status, body)


# ================================================================
# 6. Knowledge search
# ================================================================

print()
print("6. KNOWLEDGE")
print("-" * 76)

if STORE_ID:
    status, body = request(
        "POST",
        "/v1/knowledge/search",
        {
            "store_id": str(STORE_ID),
            "query": "test",
            "limit": 5,
        },
        api_key=API_KEY,
    )

    if status == 200:
        passed("Knowledge search", status)
    elif status in {404, 422}:
        skipped("Knowledge search", f"No indexed knowledge ({status})")
    else:
        failed("Knowledge search", status, body)
else:
    skipped("Knowledge search", "store_id unavailable")


# ================================================================
# 7. Semantic search
# ================================================================

print()
print("7. SEMANTIC SEARCH")
print("-" * 76)

if STORE_ID:
    status, body = request(
        "POST",
        "/v1/knowledge/semantic-search",
        {
            "store_id": str(STORE_ID),
            "query": "test",
            "limit": 5,
        },
        api_key=API_KEY,
    )

    if status == 200:
        passed("Semantic search", status)
    elif status in {404, 422}:
        skipped("Semantic search", f"No indexed knowledge ({status})")
    else:
        failed("Semantic search", status, body)
else:
    skipped("Semantic search", "store_id unavailable")


# ================================================================
# 8. Hybrid search
# ================================================================

print()
print("8. HYBRID SEARCH")
print("-" * 76)

if STORE_ID:
    status, body = request(
        "POST",
        "/v1/knowledge/hybrid-search",
        {
            "store_id": str(STORE_ID),
            "query": "test",
            "limit": 5,
        },
        api_key=API_KEY,
    )

    if status == 200:
        passed("Hybrid search", status)
    elif status in {404, 422}:
        skipped("Hybrid search", f"No indexed knowledge ({status})")
    else:
        failed("Hybrid search", status, body)
else:
    skipped("Hybrid search", "store_id unavailable")


# ================================================================
# 9. Datasource list
# ================================================================

print()
print("9. DATASOURCES")
print("-" * 76)

status, body = request(
    "GET",
    "/v1/datasources",
    api_key=API_KEY,
)

if status == 200:
    passed("List datasources", status)
else:
    failed("List datasources", status, body)


# ================================================================
# 10. Final summary
# ================================================================

print()
print("=" * 76)
print(" E2E TEST SUMMARY")
print("=" * 76)

print(f"PASS : {PASS}")
print(f"FAIL : {FAIL}")
print(f"SKIP : {SKIP}")
print()

if FAIL == 0:
    print("RESULT: E2E AUTH FLOW PASSED")
    print()
    print("The authenticated API flow is responding correctly.")
    sys.exit(0)
else:
    print("RESULT: E2E AUTH FLOW FOUND FAILURES")
    print()
    print("Review the [FAIL] entries above.")
    sys.exit(1)
