from app.db.database import engine
from app.db.database import Base

from app.knowledge.models import KnowledgePage
from app.knowledge.chunk import KnowledgeChunk


def init_db():

    Base.metadata.create_all(
        bind=engine
    )
