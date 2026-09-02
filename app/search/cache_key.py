import hashlib


def search_cache_key(
    tenant_id,
    query,
):

    normalized = (
        query
        .strip()
        .lower()
    )

    digest = hashlib.sha256(
        normalized.encode()
    ).hexdigest()

    return (
        f"search:"
        f"{tenant_id}:"
        f"{digest}"
    )
