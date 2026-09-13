import hashlib


def normalize_query(text: str):

    return (
        text.lower()
        .strip()
    )


def build_cache_key(
    tenant_id,
    query,
    data_version,
    language,
):

    normalized = normalize_query(query)

    raw = (
        f"{tenant_id}:"
        f"{normalized}:"
        f"{data_version}:"
        f"{language}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()
