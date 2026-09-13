"""
One-off backfill: encrypt any `datasources.connection_url` rows that
still hold plaintext (written before CredentialStore was wired up).

Safe to run multiple times — already-encrypted rows (prefixed
`enc$v1$`) are skipped. Run this once right after deploying the
encryption-at-rest fix, then again any time you suspect a row slipped
through (e.g. restored from an old backup).

Usage:
    python -m scripts.encrypt_legacy_connection_urls          # dry run
    python -m scripts.encrypt_legacy_connection_urls --apply  # writes changes

Requires the same env as the app (DATABASE_URL, CREDENTIAL_ENCRYPTION_KEY).
Take a DB backup before running with --apply.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes. Without this flag, only reports "
        "what would change.",
    )
    args = parser.parse_args()

    # Imported here (not at module top) so --help works without a
    # configured DB/encryption key.
    from app.connectors.credential_store import get_credential_store
    from app.db.database import SessionLocal
    from app.db.models import DataSource

    store = get_credential_store()
    db = SessionLocal()

    try:
        rows = (
            db.query(DataSource)
            .filter(DataSource.connection_url.isnot(None))
            .all()
        )

        legacy = [r for r in rows if not store.is_encrypted(r.connection_url)]

        print(f"scanned {len(rows)} datasource row(s) with a connection_url")
        print(f"found {len(legacy)} legacy plaintext row(s)")

        if not legacy:
            print("nothing to do")
            return 0

        for ds in legacy:
            print(
                f"  - datasource={ds.id} store={ds.store_id} "
                f"connector_type={ds.connector_type}"
            )

        if not args.apply:
            print("\nDry run only — re-run with --apply to encrypt these rows.")
            return 0

        for ds in legacy:
            ds.connection_url = store.encrypt(ds.connection_url)

        db.commit()
        print(f"\nencrypted {len(legacy)} row(s) and committed.")

        # Verify: every row should now decrypt back to something usable
        # and read as encrypted.
        db.expire_all()
        still_legacy = [
            r
            for r in (
                db.query(DataSource)
                .filter(DataSource.connection_url.isnot(None))
                .all()
            )
            if not store.is_encrypted(r.connection_url)
        ]
        if still_legacy:
            print(
                f"WARNING: {len(still_legacy)} row(s) still not encrypted "
                "after commit — investigate before considering this done.",
                file=sys.stderr,
            )
            return 1

        print("verified: no plaintext connection_url rows remain.")
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
