from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.chat.models import ChatMessage
from app.api.routes.messages import _apply_after_cursor


def test_after_cursor_keeps_later_rows_with_same_timestamp():
    engine = create_engine("sqlite:///:memory:")
    ChatMessage.__table__.create(engine)
    timestamp = datetime(2026, 1, 1, 12, 0, 0)

    with Session(engine) as db:
        first = ChatMessage(id="00000000-0000-0000-0000-000000000001", session_id="s1", role="merchant", content="first", created_at=timestamp)
        second = ChatMessage(id="00000000-0000-0000-0000-000000000002", session_id="s1", role="merchant", content="second", created_at=timestamp)
        later = ChatMessage(id="00000000-0000-0000-0000-000000000003", session_id="s1", role="merchant", content="later", created_at=datetime(2026, 1, 1, 12, 0, 1))
        db.add_all([first, second, later])
        db.commit()

        query = db.query(ChatMessage).filter(ChatMessage.session_id == "s1")
        rows = _apply_after_cursor(query, db, "s1", first.id).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).all()

        assert [row.id for row in rows] == [second.id, later.id]
