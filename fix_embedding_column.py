from app.core.config import settings
from sqlalchemy import create_engine, text

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
