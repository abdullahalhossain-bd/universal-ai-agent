"""
Create a demo store + API key for local development.

Run with:  python create_test_tenant.py

The script uses the canonical `app.db.database` Base + `app.core.security`
key generator (which returns a 3-tuple of `raw_key, prefix, key_hash`),
and the canonical `Store` / `APIKey` ORM models. The output is the raw
API key — copy it into the `x-api-key` header of subsequent API calls.
"""

import uuid

from app.core.security import (
    generate_api_key,
)
from app.db.database import (
    Base,
    SessionLocal,
    engine,
)
from app.db.models import (
    APIKey,
    Store,
)


def main():
    # Register the ORM tables with the shared metadata, then create them.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        store = Store(
            id=str(uuid.uuid4()),
            name="Demo Store",
            website_url=None,
            status="active",
        )

        db.add(store)
        db.flush()

        raw_key, prefix, key_hash = generate_api_key()

        api_key = APIKey(
            id=str(uuid.uuid4()),
            store_id=store.id,
            key_prefix=prefix,
            key_hash=key_hash,
            name="Demo API Key",
        )

        db.add(api_key)

        db.commit()

        print()
        print("=" * 60)
        print("TEST STORE CREATED")
        print("=" * 60)
        print(f"Store ID : {store.id}")
        print(f"API Key  : {raw_key}")
        print("=" * 60)
        print()
        print(
            "Use this key in the 'x-api-key' header of subsequent API calls."
        )
        print()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
