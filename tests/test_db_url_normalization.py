"""Regression tests: merchant-pasted bare DB schemes must be normalized.

`mysql://...` resolves to the legacy MySQL-python driver under
SQLAlchemy and crashes discovery with ModuleNotFoundError; `postgres://`
is rejected in SQLAlchemy 2.x. Both must be rewritten before they reach
create_engine (see app/core/db_url.py).
"""
from sqlalchemy.engine import make_url

from app.core.db_url import normalize_database_url


def test_mysql_scheme_becomes_pymysql():
    out = normalize_database_url(
        "mysql://u752807333_ai:Me1Boss1%40@srv502.hstgr.io:3306/u752807333_ai"
    )
    assert out == (
        "mysql+pymysql://u752807333_ai:Me1Boss1%40@srv502.hstgr.io:3306/u752807333_ai"
    )


def test_postgres_scheme_becomes_postgresql():
    assert normalize_database_url(
        "postgres://user:pw@db.example.com:5432/shop"
    ) == "postgresql://user:pw@db.example.com:5432/shop"


def test_mariadb_scheme_becomes_pymysql():
    assert normalize_database_url(
        "mariadb://user@db.example.com/shop"
    ) == "mysql+pymysql://user@db.example.com/shop"


def test_driver_qualified_urls_untouched():
    for url in (
        "mysql+pymysql://u:p@h/db",
        "postgresql://u:p@h/db",
        "postgresql+psycopg://u:p@h/db",
        "sqlite:///local.db",
    ):
        assert normalize_database_url(url) == url


def test_edge_cases_untouched():
    assert normalize_database_url(None) is None
    assert normalize_database_url("") == ""
    assert normalize_database_url("not a url") == "not a url"


def test_normalized_urls_are_parseable():
    for raw in (
        "mysql://u:Me1Boss1%40@srv502.hstgr.io:3306/db",
        "postgres://u:p@h:5432/db",
    ):
        url = make_url(normalize_database_url(raw))
        assert url.host
        assert url.database
