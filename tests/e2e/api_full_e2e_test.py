import json
import sys
import urllib.request
import urllib.error
import uuid
import tempfile
import os

BASE = "http://127.0.0.1:8000"

PASS = 0
FAIL = 0
SKIP = 0


def request(method, path, data=None, api_key=None, timeout=60):
    url = BASE + path
    headers = {"Accept": "application/json"}

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
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw

    except Exception as e:
        return None, str(e)


def multipart_upload(path, filename, content, api_key, conversation_id=None):
    boundary = "----E2ETestBoundary" + uuid.uuid4().hex

    parts = []

    parts.append(
        (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f'Content-Type: image/png\r\n\r\n'
        ).encode()
        + content
        + b"\r\n"
    )

    if conversation_id:
        parts.append(
            (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="conversation_id"\r\n\r\n'
                f'{conversation_id}\r\n'
            ).encode()
        )

    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)

    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "x-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw

    except Exception as e:
        return None, str(e)


def find_value(obj, names):
    if isinstance(obj, dict):
        for name in names:
            if obj.get(name):
                return obj[name]

        for value in obj.values():
            found = find_value(value, names)
            if found:
                return found

    elif isinstance(obj, list):
        for value in obj:
            found = find_value(value, names)
            if found:
                return found

    return None


def result(name, ok, status=None, body=None, skip=False):
    global PASS, FAIL, SKIP

    if skip:
        SKIP += 1
        print(f"[SKIP] {name:<48} {status}")
        return

    if ok:
        PASS += 1
        print(f"[PASS] {name:<48} {status}")
    else:
        FAIL += 1
        print(f"[FAIL] {name:<48} {status}")
        if body is not None:
            print(str(body)[:2000])


print()
print("=" * 80)
print(" Universal Commerce AI - Image + Discovery + Mapping E2E")
print("=" * 80)
print()

# ================================================================
# 1. Create isolated store
# ================================================================

print("1. TEST STORE")
print("-" * 80)

store_name = "Full E2E " + uuid.uuid4().hex[:8]

status, body = request(
    "POST",
    "/v1/stores",
    {
        "name": store_name,
        "website_url": "https://example.com",
        "plan": "starter",
    },
)

if status not in {200, 201}:
    result("Create test store", False, status, body)
    print("\nCannot continue without API key.")
    sys.exit(1)

result("Create test store", True, status)

API_KEY = find_value(body, ["api_key", "apiKey", "key"])
STORE_ID = find_value(body, ["store_id", "id"])

if not API_KEY or not STORE_ID:
    result(
        "Extract store credentials",
        False,
        "missing",
        body,
    )
    sys.exit(1)

print(f"       store_id: {STORE_ID}")
print(f"       api_key : FOUND")


# ================================================================
# 2. Image upload
# ================================================================

print()
print("2. IMAGE UPLOAD")
print("-" * 80)

# Minimal valid 1x1 PNG.
png_1x1 = bytes.fromhex(
    "89504E470D0A1A0A"
    "0000000D49484452000000010000000108060000001F15C489"
    "0000000D49444154789C6360000000020001E221BC33"
    "0000000049454E44AE426082"
)

conversation_id = "image-e2e-" + uuid.uuid4().hex

status, body = multipart_upload(
    "/v1/images",
    "e2e-test.png",
    png_1x1,
    API_KEY,
    conversation_id,
)

if status == 200:
    result("Upload test image", True, status)
else:
    result("Upload test image", False, status, body)

IMAGE_ID = find_value(body, ["image_id", "id"]) if status == 200 else None

print(f"       image_id: {IMAGE_ID or '(not returned)'}")


# ================================================================
# 3. Image analysis
# ================================================================

print()
print("3. IMAGE ANALYSIS")
print("-" * 80)

if not IMAGE_ID:
    result(
        "Analyze uploaded image",
        False,
        "SKIPPED",
        "No image_id returned",
        skip=True,
    )
else:
    status, body = request(
        "POST",
        f"/v1/images/{IMAGE_ID}/analyze",
        {
            "conversation_id": conversation_id,
            "question": "What is in this image?",
        },
        API_KEY,
        timeout=90,
    )

    if status == 200:
        result("Analyze uploaded image", True, status)
        print("       Analysis response:")
        print(str(body)[:2500])
    elif status in {429, 502, 503, 504}:
        result(
            "Analyze uploaded image",
            False,
            f"provider {status}",
            body,
            skip=True,
        )
    else:
        result("Analyze uploaded image", False, status, body)


# ================================================================
# 4. Datasource test connection
# ================================================================

print()
print("4. DATASOURCE CONNECTION")
print("-" * 80)

# We deliberately do NOT create a real datasource yet.
# First test the endpoint's validation/authenticated boundary.

status, body = request(
    "POST",
    "/v1/datasources/test",
    {
        "connector_type": "postgresql",
        "connection_url": "postgresql://invalid-e2e-host.invalid:5432/test",
        "api_base_url": None,
    },
    API_KEY,
    timeout=15,
)

if status in {400, 422, 502, 503}:
    result(
        "Datasource connection handling",
        True,
        status,
        body,
    )
elif status == 200:
    result(
        "Datasource connection handling",
        True,
        status,
        body,
    )
else:
    result(
        "Datasource connection handling",
        False,
        status,
        body,
    )


# ================================================================
# 5. Datasource CRUD - create a deliberately non-working test
# ================================================================

print()
print("5. DATASOURCE CREATE")
print("-" * 80)

datasource_payload = {
    "name": "E2E Test Datasource",
    "connector_type": "postgresql",
    "connection_url": "postgresql://invalid-e2e-host.invalid:5432/test",
    "api_base_url": None,
    "table_name": "products",
    "mapping": {},
    "active": False,
    "full_sync": False,
    "skip_connection_test": True,
}

status, body = request(
    "POST",
    "/v1/datasources",
    datasource_payload,
    API_KEY,
    timeout=30,
)

if status in {200, 201}:
    result("Create test datasource", True, status)
    DATASOURCE_ID = find_value(body, ["datasource_id", "id"])
    print(f"       datasource_id: {DATASOURCE_ID}")
else:
    result("Create test datasource", False, status, body)
    DATASOURCE_ID = None


# ================================================================
# 6. Datasource get
# ================================================================

print()
print("6. DATASOURCE READ")
print("-" * 80)

if DATASOURCE_ID:
    status, body = request(
        "GET",
        f"/v1/datasources/{DATASOURCE_ID}",
        api_key=API_KEY,
    )

    result(
        "Get test datasource",
        status == 200,
        status,
        body,
    )
else:
    result(
        "Get test datasource",
        False,
        "SKIPPED",
        "No datasource_id",
        skip=True,
    )


# ================================================================
# 7. Datasource discovery
# ================================================================

print()
print("7. DATASOURCE DISCOVERY")
print("-" * 80)

if DATASOURCE_ID:
    status, body = request(
        "POST",
        f"/v1/datasources/{DATASOURCE_ID}/discover",
        api_key=API_KEY,
        timeout=30,
    )

    if status in {400, 404, 422, 502, 503}:
        result(
            "Datasource discovery error handling",
            True,
            status,
            body,
        )
    elif status == 200:
        result(
            "Datasource discovery",
            True,
            status,
            body,
        )
    else:
        result(
            "Datasource discovery",
            False,
            status,
            body,
        )
else:
    result(
        "Datasource discovery",
        False,
        "SKIPPED",
        "No datasource_id",
        skip=True,
    )


# ================================================================
# 8. Generic discovery
# ================================================================

print()
print("8. DATABASE DISCOVERY")
print("-" * 80)

status, body = request(
    "POST",
    "/v1/discovery/scan",
    {
        "connection_url": "postgresql://invalid-e2e-host.invalid:5432/test",
        "table": "products",
    },
    API_KEY,
    timeout=30,
)

if status in {400, 404, 422, 502, 503}:
    result(
        "Database discovery error handling",
        True,
        status,
        body,
    )
elif status == 200:
    result(
        "Database discovery",
        True,
        status,
        body,
    )
else:
    result(
        "Database discovery",
        False,
        status,
        body,
    )


# ================================================================
# 9. Mapping suggest
# ================================================================

print()
print("9. MAPPING SUGGEST")
print("-" * 80)

mapping_columns = [
    {"name": "id", "type": "integer"},
    {"name": "name", "type": "text"},
    {"name": "price", "type": "numeric"},
    {"name": "stock", "type": "integer"},
]

sample_data = {
    "id": ["1", "2"],
    "name": ["Test Product", "Another Product"],
    "price": ["10.00", "20.00"],
    "stock": ["5", "8"],
}

status, body = request(
    "POST",
    "/v1/mapping/suggest",
    {
        "store_id": str(STORE_ID),
        "table": "products",
        "columns": mapping_columns,
        "sample_data": sample_data,
        "overrides": {},
    },
    API_KEY,
    timeout=60,
)

if status == 200:
    result("Suggest mapping", True, status)
    print("       Mapping response:")
    print(str(body)[:3000])
else:
    result("Suggest mapping", False, status, body)


# ================================================================
# 10. Mapping confirm
# ================================================================

print()
print("10. MAPPING CONFIRM")
print("-" * 80)

status, body = request(
    "POST",
    "/v1/mapping/confirm",
    {
        "store_id": str(STORE_ID),
        "table": "products",
        "columns": mapping_columns,
        "sample_data": sample_data,
        "choices": {
            "id": "id",
            "name": "name",
            "price": "price",
            "stock": "stock",
        },
    },
    API_KEY,
    timeout=60,
)

if status == 200:
    result("Confirm mapping", True, status)
    print("       Confirm response:")
    print(str(body)[:3000])
else:
    result("Confirm mapping", False, status, body)


# ================================================================
# 11. Cleanup test datasource
# ================================================================

print()
print("11. CLEANUP")
print("-" * 80)

if DATASOURCE_ID:
    status, body = request(
        "DELETE",
        f"/v1/datasources/{DATASOURCE_ID}",
        api_key=API_KEY,
        timeout=30,
    )

    if status in {200, 204}:
        result("Delete test datasource", True, status)
    else:
        result("Delete test datasource", False, status, body)
else:
    result(
        "Delete test datasource",
        False,
        "SKIPPED",
        "No datasource created",
        skip=True,
    )


# ================================================================
# Summary
# ================================================================

print()
print("=" * 80)
print(" FINAL SUMMARY")
print("=" * 80)

print(f"PASS : {PASS}")
print(f"FAIL : {FAIL}")
print(f"SKIP : {SKIP}")
print()

if FAIL == 0:
    print("RESULT: IMAGE + DISCOVERY + MAPPING E2E PASSED")
    sys.exit(0)
else:
    print("RESULT: E2E TEST FOUND FAILURES")
    sys.exit(1)
