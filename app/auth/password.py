"""
Password hashing for dashboard `User` accounts.

Deliberately separate from `app.core.security.hash_api_key`: API keys
are high-entropy random secrets hashed with a fast, unsalted SHA-256
(safe there only because a `pk_live_...` key already has ~256 bits of
entropy, unlike a human-chosen password). Passwords need a slow,
salted KDF instead — bcrypt, via the `bcrypt` package directly (no
passlib dependency).
"""

from __future__ import annotations

import bcrypt

# bcrypt silently truncates input at 72 bytes; reject anything longer
# up front rather than accepting a password whose tail is ignored.
_MAX_PASSWORD_BYTES = 72
_MIN_PASSWORD_LENGTH = 8


class WeakPasswordError(ValueError):
    """Raised by `hash_password` when a password fails basic policy."""


def validate_password_strength(password: str) -> None:
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Password must be at least {_MIN_PASSWORD_LENGTH} characters."
        )
    if len(password.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        raise WeakPasswordError("Password is too long.")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        # Malformed hash (should never happen for a row we wrote) —
        # fail closed rather than raising past the auth boundary.
        return False
