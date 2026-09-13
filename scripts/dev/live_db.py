"""Bounded database sessions for live verification harnesses only."""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_timeout=5,
    connect_args={"connect_timeout": 5},
)


@event.listens_for(engine, "connect")
def _set_statement_timeout(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET statement_timeout = 15000")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
