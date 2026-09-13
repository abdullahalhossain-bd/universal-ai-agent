import hashlib
import json


def schema_fingerprint(tables: list[dict]):

    normalized = sorted(
        [
            {
                "table": t["table"],
                "columns": sorted(t["columns"]),
            }
            for t in tables
        ],
        key=lambda t: t["table"],
    )

    raw = json.dumps(
        normalized,
        sort_keys=True,
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()
