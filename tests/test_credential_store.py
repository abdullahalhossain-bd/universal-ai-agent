"""
Proof that merchant connection secrets (DB connection strings, which
embed username/password) are encrypted before they reach a database
row, and that legacy plaintext rows are still readable so a rollout
doesn't 500 on existing data.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.connectors.credential_store import CredentialStore, get_credential_store


# ---------------------------------------------------------------------------
# CredentialStore unit behavior
# ---------------------------------------------------------------------------


def _store() -> CredentialStore:
    return CredentialStore(Fernet.generate_key())


def test_encrypt_then_decrypt_round_trips():
    store = _store()
    secret = "postgresql://merchant_user:s3cr3t-pw@db.merchant.example/prod"
    ciphertext = store.encrypt(secret)

    assert ciphertext != secret
    assert secret not in ciphertext  # plaintext must not leak into ciphertext
    assert store.decrypt(ciphertext) == secret


def test_ciphertext_is_not_the_raw_connection_string():
    """
    This is the actual vulnerability check: what would be written to
    the `connection_url` column must never contain the plaintext
    password.
    """
    store = _store()
    secret = "mysql://root:hunter2@10.0.0.5:3306/catalog"
    ciphertext = store.encrypt(secret)
    assert "hunter2" not in ciphertext
    assert "root" not in ciphertext


def test_same_plaintext_encrypts_differently_each_time():
    # Fernet includes a random IV — two encryptions of the same
    # secret must not be comparable/identical ciphertext.
    store = _store()
    a = store.encrypt("postgresql://u:p@host/db")
    b = store.encrypt("postgresql://u:p@host/db")
    assert a != b


def test_decrypt_rejects_tampered_ciphertext():
    store = _store()
    ciphertext = store.encrypt("postgresql://u:p@host/db")
    tampered = ciphertext[:-2] + ("aa" if ciphertext[-2:] != "aa" else "bb")
    with pytest.raises(ValueError):
        store.decrypt(tampered)


def test_decrypt_with_wrong_key_fails_closed():
    store_a = _store()
    store_b = _store()
    ciphertext = store_a.encrypt("postgresql://u:p@host/db")
    with pytest.raises(ValueError):
        store_b.decrypt(ciphertext)


def test_legacy_plaintext_rows_still_read_but_flagged(caplog):
    # Rows written before this fix (no "enc$v1$" prefix) must still be
    # usable so existing datasources don't break — but this should be
    # visibly logged so it gets migrated, not silently tolerated.
    store = _store()
    legacy_value = "postgresql://merchant:pw@host/db"
    with caplog.at_level("WARNING"):
        assert store.decrypt(legacy_value) == legacy_value
    assert any("legacy plaintext" in r.message for r in caplog.records)


def test_encrypt_decrypt_none_is_none():
    store = _store()
    assert store.encrypt(None) is None
    assert store.decrypt(None) is None


def test_bad_key_raises_helpful_error():
    with pytest.raises(ValueError):
        CredentialStore("not-a-valid-fernet-key")


def test_get_credential_store_uses_configured_key():
    # Wired to app.core.config.settings.credential_encryption_key via
    # tests/conftest.py's CREDENTIAL_ENCRYPTION_KEY env var.
    store = get_credential_store()
    ciphertext = store.encrypt("postgresql://u:p@host/db")
    assert store.decrypt(ciphertext) == "postgresql://u:p@host/db"


# ---------------------------------------------------------------------------
# DataSourceService: encrypted at the persistence boundary
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.database import Base
    from app.db.models import DataSource, Store  # noqa: F401  (register tables)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _make_store(db_session):
    from app.db.models import Store

    store = Store(name="Test Merchant")
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)
    return store


def test_create_persists_ciphertext_not_plaintext(db_session):
    from app.datasources.service import DataSourceService

    store = _make_store(db_session)
    service = DataSourceService(db_session)
    secret_url = "postgresql://merchant_admin:sup3r-secret@merchantdb.example/prod"

    ds = service.create(
        store.id,
        name="primary",
        connector_type="postgresql",
        connection_url=secret_url,
        validate_connection=False,  # no real DB to connect to in this test
    )

    # The plaintext secret must never be sitting in the row as-is.
    assert ds.connection_url != secret_url
    assert "sup3r-secret" not in ds.connection_url
    assert "merchant_admin" not in ds.connection_url

    # But it must still be usable for an actual connection later.
    assert DataSourceService.decrypt_connection_url(ds) == secret_url


def test_update_re_encrypts_new_connection_url(db_session, monkeypatch):
    from app.datasources.service import DataSourceService

    store = _make_store(db_session)
    service = DataSourceService(db_session)
    ds = service.create(
        store.id,
        name="primary",
        connector_type="postgresql",
        connection_url="postgresql://u:pw1@host/db",
        validate_connection=False,
    )

    # update() re-validates the new connection_url against a live DB;
    # stub that out here since this test is only about the
    # encrypt-at-rest behavior, not connectivity.
    monkeypatch.setattr(
        DataSourceService, "_test_connection_sync", lambda self, *a, **kw: True
    )

    new_secret = "postgresql://u:pw2-new-secret@host/db"
    ds = service.update(
        store.id,
        ds.id,
        connection_url=new_secret,
    )

    assert "pw2-new-secret" not in ds.connection_url
    assert DataSourceService.decrypt_connection_url(ds) == new_secret


def test_public_datasource_dict_never_exposes_plaintext(db_session):
    from app.datasources.redaction import public_datasource_dict
    from app.datasources.service import DataSourceService

    store = _make_store(db_session)
    service = DataSourceService(db_session)
    ds = service.create(
        store.id,
        name="primary",
        connector_type="postgresql",
        connection_url="postgresql://admin:top-secret-pw@merchantdb.example/prod",
        validate_connection=False,
    )

    body = public_datasource_dict(ds)
    assert "top-secret-pw" not in body["connection_url"]
    assert "admin" not in body["connection_url"]
    # Host is still shown so the merchant can recognize which DB this is.
    assert "merchantdb.example" in body["connection_url"]


# ---------------------------------------------------------------------------
# Backfill script
# ---------------------------------------------------------------------------


def test_backfill_script_encrypts_legacy_rows_and_is_idempotent(
    db_session, monkeypatch
):
    """
    Simulates a DB with pre-fix plaintext rows, runs the backfill logic
    in-process (same code path as scripts/encrypt_legacy_connection_urls.py),
    and checks: legacy rows get encrypted, already-encrypted rows are
    left alone, and a second run finds nothing left to do.
    """
    from app.connectors.credential_store import get_credential_store
    from app.db.models import DataSource

    store_row = _make_store(db_session)
    cred_store = get_credential_store()

    legacy = DataSource(
        id="ds-legacy",
        store_id=store_row.id,
        name="legacy",
        connector_type="postgresql",
        connection_url="postgresql://u:legacy-secret@host/db",  # plaintext
    )
    already_encrypted_value = cred_store.encrypt(
        "postgresql://u:already-safe@host/db"
    )
    encrypted = DataSource(
        id="ds-encrypted",
        store_id=store_row.id,
        name="already-encrypted",
        connector_type="postgresql",
        connection_url=already_encrypted_value,
    )
    db_session.add_all([legacy, encrypted])
    db_session.commit()

    def backfill_pass():
        rows = (
            db_session.query(DataSource)
            .filter(DataSource.connection_url.isnot(None))
            .all()
        )
        legacy_rows = [
            r for r in rows if not cred_store.is_encrypted(r.connection_url)
        ]
        for ds in legacy_rows:
            ds.connection_url = cred_store.encrypt(ds.connection_url)
        db_session.commit()
        return len(legacy_rows)

    changed = backfill_pass()
    assert changed == 1

    db_session.expire_all()
    reloaded_legacy = db_session.get(DataSource, "ds-legacy")
    reloaded_encrypted = db_session.get(DataSource, "ds-encrypted")

    assert cred_store.is_encrypted(reloaded_legacy.connection_url)
    assert "legacy-secret" not in reloaded_legacy.connection_url
    assert cred_store.decrypt(reloaded_legacy.connection_url) == (
        "postgresql://u:legacy-secret@host/db"
    )
    # Untouched row's ciphertext is unchanged (not re-encrypted).
    assert reloaded_encrypted.connection_url == already_encrypted_value

    # Second pass: idempotent, nothing left to change.
    assert backfill_pass() == 0
