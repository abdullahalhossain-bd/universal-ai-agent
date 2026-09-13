"""One-off ops script: converts knowledge_chunks.embedding to vector(384).

DANGEROUS: it DROPS the embedding column, destroying every stored vector.
Superseded by alembic migrations 0002 / 0019 / 0043, which perform the same
conversion with guards (and 0043 additionally fixes the cosine index).
Run only when explicitly intended, by setting the confirmation env var:
    CONFIRM_DESTROY_EMBEDDINGS=1 python scripts/dev/fix_embedding_column.py
"""
import os

from app.core.config import settings
from sqlalchemy import create_engine, text

if os.getenv("CONFIRM_DESTROY_EMBEDDINGS") != "1":
    raise SystemExit(
        "Refusing to run: this script DROPS knowledge_chunks.embedding and "
        "destroys all stored embeddings. Alembic migrations 0002/0019/0043 "
        "handle the conversion safely. If you truly need this, re-run with "
        "CONFIRM_DESTROY_EMBEDDINGS=1."
    )

engine = create_engine(settings.database_url)

with engine.begin() as conn:
    conn.execute(text("""
        ALTER TABLE knowledge_chunks
        DROP COLUMN embedding
    """))

    conn.execute(text("""
        ALTER TABLE knowledge_chunks
        ADD COLUMN embedding vector(384)
    """))

print("OK: embedding -> vector(384)")
