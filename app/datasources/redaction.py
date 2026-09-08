"""
Secret redaction for connection URLs and API responses.

Never log or return plaintext passwords / API keys.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from app.connectors.credential_store import get_credential_store

REDACTED = "***"


def redact_url(url: str | None) -> str | None:
    """
    Strip userinfo (username:password@) from a connection URL.
    Returns None if url is None.
    """
    if url is None:
        return None
    if not url:
        return ""

    try:
        parsed = urlparse(url)
    except Exception:
        return REDACTED

    if parsed.password is None and parsed.username is None:
        # Also hide query params that look like secrets.
        return _redact_query_secrets(url)

    # Rebuild without password; keep username only if present without password
    # is uncommon for DB URLs — redact both.
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    netloc = host
    redacted = urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )
    return _redact_query_secrets(redacted)


def _redact_query_secrets(url: str) -> str:
    lower = url.lower()
    for key in ("password=", "api_key=", "apikey=", "token=", "secret="):
        if key in lower:
            # crude but safe: hide everything after the key
            idx = lower.index(key)
            return url[: idx + len(key)] + REDACTED
    return url


def public_datasource_dict(ds) -> dict:
    """Serialize a DataSource ORM row for API responses (secrets redacted)."""
    mapping = ds.mapping
    if mapping is not None and not isinstance(mapping, dict):
        mapping = dict(mapping)

    return {
        "id": ds.id,
        "store_id": ds.store_id,
        "name": ds.name,
        "connector_type": ds.connector_type,
        # ds.connection_url is ciphertext at rest — decrypt only to
        # immediately redact it; the plaintext never leaves this
        # function.
        "connection_url": redact_url(
            get_credential_store().decrypt(ds.connection_url)
        ),
        "api_base_url": ds.api_base_url,
        "credential_ref": ds.credential_ref,
        "table_name": ds.table_name,
        "mapping": mapping,
        "active": ds.active,
        "full_sync": ds.full_sync,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
        "last_sync_at": (
            ds.last_sync_at.isoformat() if ds.last_sync_at else None
        ),
        "last_sync_status": ds.last_sync_status,
        "last_sync_error": ds.last_sync_error,
    }
