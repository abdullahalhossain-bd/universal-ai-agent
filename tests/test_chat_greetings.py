"""
Tests for chat greeting handling ("Hi", "Hello", "Kemon aso", ...).

A pure greeting must get a friendly conversational reply — not a
store-data dump, not an LLM call, and not a 503. These tests pin:

1. Detection: short greeting-only messages are recognized; real
   queries that merely CONTAIN a greeting word ("hello, show me
   laptops") fall through to the normal pipeline.
2. Reply selection: "kemon aso" / "how are you" get the self-
   introduction ("I'm fine") reply; plain hellos get the welcome.
3. End-to-end: ChatService.handle() returns type="greeting" with
   empty products/sources and persists both turns.
"""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import Store


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _service(db_session):
    from app.chat.service import ChatService

    return ChatService(db=db_session)


def _make_store(db):
    store = Store(name="Greeting Store")
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


# ------------------------------------------------------------------
# 1. Detection
# ------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "Hi",
    "hi",
    "hello",
    "Hello!",
    "Hello??",
    "Hey",
    "Hii",
    "Salam",
    "Assalamu alaikum",
    "Kemon aso",
    "kemon achen",
    "Kmon acho",
    "Ki khobor",
    "How are you",
    "how are you doing",
    "hi kemon aso",
    "good morning",
    "Good evening",
])
def test_greeting_detection_positive(db_session, msg):
    svc = _service(db_session)
    assert svc._is_greeting(msg), f"{msg!r} should be a greeting"


@pytest.mark.parametrize("msg", [
    "hello, show me laptops",
    "hello ami laptop khujtechi",
    "Do you have any products in stock?",
    "How much is Asus Gaming?",
    "how much laptop er dam",
    "kemon er dam koto",
    "laptop",
    "ami ekta laptop chai",
    "Tell me about your shop",
    "",
])
def test_greeting_detection_negative(db_session, msg):
    svc = _service(db_session)
    assert not svc._is_greeting(msg), f"{msg!r} must NOT be a greeting"


# ------------------------------------------------------------------
# 2. Reply selection
# ------------------------------------------------------------------

def test_greeting_reply_how_are_you_gets_self_intro(db_session):
    svc = _service(db_session)
    for msg in ("Kemon aso", "how are you", "Ki khobor", "kemon achen"):
        reply = svc._greeting_reply(msg)
        assert "ভালো" in reply, (
            f"{msg!r} should get the self-introduction reply, got {reply!r}"
        )


def test_greeting_reply_plain_hello_gets_welcome(db_session):
    svc = _service(db_session)
    for msg in ("Hi", "hello", "Salam", "good morning"):
        reply = svc._greeting_reply(msg)
        assert "সাহায্য" in reply or "help" in reply.lower(), (
            f"{msg!r} should get the welcome reply, got {reply!r}"
        )


# ------------------------------------------------------------------
# 3. End-to-end through handle()
# ------------------------------------------------------------------

@pytest_asyncio.fixture
async def _store(db_session):
    return _make_store(db_session)


@pytest.mark.asyncio
async def test_handle_greeting_returns_greeting_type(db_session, _store):
    svc = _service(db_session)
    request = SimpleNamespace(message="Kemon aso", conversation_id=None)
    out = await svc.handle(store_id=_store.id, request=request)

    assert out["type"] == "greeting"
    assert "ভালো" in out["message"]
    assert out["products"] == []
    assert out["sources"] == []
    assert out["conversation_id"]


@pytest.mark.asyncio
async def test_handle_greeting_persists_both_turns(db_session, _store):
    svc = _service(db_session)
    request = SimpleNamespace(message="Hi", conversation_id="conv-greet-1")
    await svc.handle(store_id=_store.id, request=request)

    from app.chat.models import ChatMessage, ChatSession

    session = (
        db_session.query(ChatSession)
        .filter(ChatSession.conversation_key == "conv-greet-1")
        .first()
    )
    assert session is not None

    roles = [
        (m.role, m.content)
        for m in db_session.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at)
        .all()
    ]
    assert [r for r, _ in roles] == ["user", "assistant"]
    assert roles[0][1] == "Hi"
    assert "help" in roles[1][1].lower() or "সাহায্য" in roles[1][1]


@pytest.mark.asyncio
async def test_handle_query_containing_hello_is_not_greeting(
    db_session, _store,
):
    svc = _service(db_session)
    request = SimpleNamespace(
        message="hello, show me laptops",
        conversation_id="conv-greet-2",
    )
    out = await svc.handle(store_id=_store.id, request=request)

    assert out["type"] != "greeting", (
        "a real query that merely contains 'hello' must go through "
        f"the normal pipeline, got type={out['type']!r}"
    )
