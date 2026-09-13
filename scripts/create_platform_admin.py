"""
Create (or reset the password of) a platform admin account.

There is deliberately no public HTTP signup for `platform_admins`
(see app/db/models.py's PlatformAdmin docstring) — this is the only
way to create one, and it's meant to be run from a trusted shell
against the real database, e.g.:

    docker compose exec app python -m scripts.create_platform_admin \\
        --email you@example.com

You'll be prompted for a password (not taken as a CLI arg, so it
never ends up in shell history). Running it again for an email that
already exists resets that admin's password instead of erroring, so
this also doubles as the "I forgot my password" recovery path.

Requires the same env as the app (DATABASE_URL).
"""

from __future__ import annotations

import argparse
import getpass
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Admin login email")
    args = parser.parse_args()

    email = args.email.strip().lower()
    if "@" not in email:
        print(f"'{email}' doesn't look like an email address.", file=sys.stderr)
        return 1

    password = getpass.getpass("Password (min 8 chars): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords did not match.", file=sys.stderr)
        return 1

    # Imported after arg parsing so `--help` works without a DB.
    from app.auth.password import WeakPasswordError, hash_password
    from app.db.database import SessionLocal
    from app.db.models import PlatformAdmin

    try:
        password_hash = hash_password(password)
    except WeakPasswordError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        admin = db.query(PlatformAdmin).filter(PlatformAdmin.email == email).first()
        if admin is None:
            admin = PlatformAdmin(email=email, password_hash=password_hash)
            db.add(admin)
            db.commit()
            print(f"Created platform admin: {email}")
        else:
            admin.password_hash = password_hash
            db.add(admin)
            db.commit()
            print(f"Password updated for existing platform admin: {email}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())