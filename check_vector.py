from app.core.config import settings
from sqlalchemy import create_engine, text

engine = create_engine(settings.database_url)

with engine.connect() as conn:
    print("EMBEDDING COLUMN:")
    print(
        conn.execute(
            text("""
                SELECT column_name, data_type, udt_name
                FROM information_schema.columns
                WHERE table_name = 'knowledge_chunks'
                  AND column_name = 'embedding'
            """)
        ).mappings().all()
    )

    print("\nPGVECTOR EXTENSION:")
    print(
        conn.execute(
            text("""
                SELECT extname
                FROM pg_extension
                WHERE extname = 'vector'
            """)
        ).fetchall()
    )
