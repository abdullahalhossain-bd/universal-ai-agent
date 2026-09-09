from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

# Register auxiliary sync models before Base.metadata.create_all() is invoked.
from app.sync.media_models import ProductMediaHealth  # noqa: E402,F401
from app.sync.issue_models import SyncIssue  # noqa: E402,F401

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
