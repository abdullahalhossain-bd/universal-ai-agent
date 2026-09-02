"""
Encryption at rest for merchant connection secrets.

`DataSource.connection_url` embeds a merchant's own database
username/password (e.g. `postgresql://user:pass@host/db`). If our own
database were ever breached, storing that string in plaintext would
hand over every merchant's DB credentials in one shot. This module
wraps it in authenticated symmetric encryption (Fernet: AES-128-CBC +
HMAC-SHA256) before it ever reaches a row, using a key that lives only
in the app's own secrets manager / environment — never in the database
itself.

Callers should not construct `CredentialStore` directly; use
`get_credential_store()`, which reads the key from `app.core.config`.
Never log `plaintext`/`ciphertext` arguments or return values.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("app.connectors.credential_store")

# Marks a value as having been through CredentialStore.encrypt(), so
# decrypt() can tell genuine ciphertext apart from legacy plaintext
# rows written before this was wired up (see decrypt() below).
_ENC_PREFIX = "enc$v1$"


class CredentialStore:
    """
    Encrypts/decrypts secrets before they are persisted.

    Real implementation backed by `cryptography.fernet.Fernet`, keyed
    by a KMS/secrets-manager-provided key in production. Never log
    decrypted credentials.
    """

    def __init__(self, encryption_key: bytes | str):
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode("utf-8")
        try:
            self._fernet = Fernet(encryption_key)
        except Exception as exc:
            raise ValueError(
                "credential_encryption_key must be a url-safe "
                "base64-encoded 32-byte key. Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\" "
                "and set it as the CREDENTIAL_ENCRYPTION_KEY env var "
                "(store it in your secrets manager, not in .env in git)."
            ) from exc

    def encrypt(self, plaintext: str | None) -> str | None:
        if plaintext is None:
            return None
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return _ENC_PREFIX + token.decode("utf-8")

    def decrypt(self, ciphertext: str | None) -> str | None:
        if ciphertext is None:
            return None

        if not ciphertext.startswith(_ENC_PREFIX):
            from app.core.config import settings

            if (settings.environment or settings.app_env).lower() in {
                "production",
                "prod",
            }:
                raise ValueError(
                    "stored datasource credential is not encrypted; "
                    "run the credential backfill before production"
                )

            logger.warning(
                "read a connection secret with no encryption prefix "
                "(legacy plaintext row); run the credential backfill"
            )
            return ciphertext

        token = ciphertext[len(_ENC_PREFIX):].encode("utf-8")
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError(
                "failed to decrypt stored connection secret: wrong "
                "encryption key, or the ciphertext was corrupted/"
                "tampered with"
            ) from exc

    def is_encrypted(self, value: str | None) -> bool:
        return bool(value) and value.startswith(_ENC_PREFIX)


_store: CredentialStore | None = None


def get_credential_store() -> CredentialStore:
    """Process-wide singleton, keyed from app.core.config.settings."""
    global _store
    if _store is None:
        from app.core.config import settings

        _store = CredentialStore(settings.credential_encryption_key)
    return _store
