"""
Central pgvector availability detection.

The `knowledge_chunks.embedding` column uses `VECTOR(384)` when the
pgvector extension is available (both the Python `pgvector` package and
the PostgreSQL extension). When either is missing, the column falls back
to `Text` so that ingestion, keyword search, and chat keep working —
only semantic (vector) search becomes unavailable.

The availability check is performed once per process and cached.
"""

import logging

import sqlalchemy

logger = logging.getLogger(__name__)

# Populated by `resolve_vector_support()` at startup.
_vector_enabled: bool | None = None


def _probe_extension(engine) -> bool:
    """
    Best-effort probe for the pgvector extension.

    Attempts `CREATE EXTENSION IF NOT EXISTS vector` (works when the
    extension binaries ship with the PostgreSQL installation and the
    connecting role has sufficient privileges), then verifies presence
    in pg_extension / pg_available_extensions.
    """

    try:
        with engine.connect() as conn:
            try:
                conn.execute(
                    sqlalchemy.text(
                        "CREATE EXTENSION IF NOT EXISTS vector"
                    )
                )
                conn.commit()
            except Exception as exc:
                logger.warning(
                    "pgvector extension could not be created "
                    "on this database (%s); vector features disabled",
                    type(exc).__name__,
                )

            present = conn.execute(
                sqlalchemy.text(
                    "SELECT 1 "
                    "FROM pg_extension "
                    "WHERE extname = 'vector'"
                )
            ).first()

            if present:
                return True

            # Extension files exist but are not installed in this DB.
            # Report unavailable so we do not emit VECTOR DDL that
            # would crash schema creation.
            return False

    except Exception as exc:
        logger.warning(
            "pgvector availability probe failed (%s); "
            "vector features disabled",
            type(exc).__name__,
        )
        return False


def resolve_vector_support(engine) -> bool:
    """
    Probe (once) and cache whether pgvector is usable.
    Returns True when `pgvector.sqlalchemy.Vector` columns can be used.
    """

    global _vector_enabled

    if _vector_enabled is not None:
        return _vector_enabled

    try:
        import pgvector.sqlalchemy  # noqa: F401

        pgvector_installed = True
    except ImportError:
        pgvector_installed = False

    if not pgvector_installed:
        _vector_enabled = False
        return _vector_enabled

    _vector_enabled = _probe_extension(engine)
    return _vector_enabled


def vector_support_enabled() -> bool:
    """
    Current cached support flag. False before resolution or when
    pgvector is unavailable.
    """

    return bool(_vector_enabled)
