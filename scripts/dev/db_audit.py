from app.core.config import settings
from sqlalchemy import create_engine, text

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

with engine.connect() as conn:

    print("=" * 70)
    print("DATABASE INFORMATION")
    print("=" * 70)

    row = conn.execute(
        text("""
            SELECT
                current_database(),
                current_user,
                version()
        """)
    ).fetchone()

    print("Database :", row[0])
    print("User     :", row[1])
    print("Version  :", row[2])

    print("\n" + "=" * 70)
    print("TABLES")
    print("=" * 70)

    tables = conn.execute(
        text("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
    ).scalars().all()

    for table in tables:

        count = conn.execute(
            text(f'SELECT COUNT(*) FROM "{table}"')
        ).scalar()

        print(f"{table:40} {count} rows")

    print("\n" + "=" * 70)
    print("EXTENSIONS")
    print("=" * 70)

    extensions = conn.execute(
        text("""
            SELECT extname
            FROM pg_extension
            ORDER BY extname
        """)
    ).scalars().all()

    for ext in extensions:
        print(ext)

    print("\n" + "=" * 70)
    print("KNOWLEDGE / DATASOURCE / SYNC TABLES")
    print("=" * 70)

    for table in tables:

        name = table.lower()

        if any(x in name for x in [
            "knowledge",
            "datasource",
            "mapping",
            "sync",
            "product",
            "connector",
        ]):

            count = conn.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar()

            print(f"{table:40} {count} rows")

    print("\n" + "=" * 70)
    print("EMBEDDING COLUMN")
    print("=" * 70)

    result = conn.execute(
        text("""
            SELECT
                column_name,
                data_type,
                udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'knowledge_chunks'
              AND column_name = 'embedding'
        """)
    ).mappings().all()

    print(result)

print("\nDATABASE AUDIT COMPLETE")
