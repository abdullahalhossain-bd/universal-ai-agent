"""
FastAPI application entrypoint.

Single active application entrypoint:
- Chat API
- Store/API-key onboarding
- Product API
- Website knowledge
- Health check
"""

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


# ---------------------------------
# Logging (must run before any other module-level
# `logger = logging.getLogger(...)` call emits anything)
# ---------------------------------

from app.core.config import (
    settings,
)
from app.core.logging_config import (
    configure_logging,
)

configure_logging(json_logs=settings.log_json)

logger = logging.getLogger("app")


# ---------------------------------
# Database
# ---------------------------------

from app.db.database import (
    Base,
    engine,
)


# ---------------------------------
# Active ORM Models
# ---------------------------------

from app.db.models import (
    Store,
    APIKey,
    Product,
    DataSource,
    ChatImage,
    User,
    PlatformAdmin,
)

from app.chat.models import (
    ChatSession,
    ChatMessage,
)

from app.knowledge.chunk import (
    KnowledgePage,
    KnowledgeChunk,
)

from app.usage.models import (
    UsageRecord,
)


# ---------------------------------
# API Routers
# ---------------------------------

from app.api.routes.products import (
    router as products_router,
)

from app.api.routes.datasources import (
    router as datasources_router,
)

from app.api.routes.stores import (
    router as stores_router,
)

from app.api.v1.knowledge import (
    router as knowledge_router,
)

from app.chat.router import (
    router as chat_router,
)

from app.api.routes.images import (
    router as images_router,
)

from app.api.routes.media import (
    router as media_router,
)

from app.api.v1.discovery import (
    router as discovery_v1_router,
)

from app.api.v1.mapping import (
    router as mapping_router,
)

from app.widget.router import (
    router as widget_router,
)

from app.api.routes.auth import (
    router as auth_router,
)

from app.api.routes.api_keys import (
    router as api_keys_router,
)

from app.api.routes.billing import (
    router as billing_router,
)

from app.api.routes.admin import (
    router as admin_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Development database initialization.

    This creates missing tables only — it never alters or
    drops existing tables. Production deployments should
    manage schema evolution exclusively through Alembic:

        alembic upgrade head

    The pgvector availability probe runs BEFORE table
    creation so `knowledge_chunks.embedding` is created as
    VECTOR(384) when the extension is usable and as Text
    otherwise (keyword search and ingestion keep working).
    """

    from app.knowledge.vector_support import (
        resolve_vector_support,
    )

    if resolve_vector_support(engine):
        logger.info(
            "pgvector detected: knowledge embeddings enabled"
        )
    else:
        logger.warning(
            "pgvector unavailable: knowledge_chunks.embedding "
            "falls back to Text; semantic search disabled"
        )

    if settings.auto_create_tables:
        if settings.environment.lower() in ("production", "prod"):
            # This is exactly the situation Alembic exists to prevent:
            # create_all() can add a missing table, but it can never
            # alter or backfill an existing one — a merchant-facing
            # column change would need to go out as a separate,
            # unreviewed manual step, or downtime, or both. Refuse to
            # boot rather than let that combination reach production
            # silently.
            raise RuntimeError(
                "auto_create_tables=true with environment=production. "
                "Set AUTO_CREATE_TABLES=false and run `alembic upgrade "
                "head` as a deploy step instead — see alembic/README.md."
            )
        # Development convenience: create missing tables only —
        # it never alters or drops existing tables.
        Base.metadata.create_all(bind=engine)
    else:
        logger.info(
            "auto_create_tables=false: skipping schema creation; "
            "run `alembic upgrade head` to manage the schema"
        )

    yield


# ---------------------------------
# FastAPI
# ---------------------------------

app = FastAPI(
    title="Universal Commerce AI API",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------
# CORS
# ---------------------------------
#
# The embeddable chat widget (app/ARCHITECTURE_CLEANUP.md item 5,
# doc item #16) runs as a <script> tag on arbitrary merchant
# websites, so the API must accept cross-origin browser requests.
# allow_credentials is False on purpose: auth is the `x-api-key`
# header, never a cookie, so a wildcard origin does not expose
# any session to a malicious page.

from app.core.security import (
    get_cors_allow_origins,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allow_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["x-api-key", "content-type"],
)


# ---------------------------------
# Request ID + access logging
# ---------------------------------
#
# Added after CORSMiddleware so it ends up outermost (Starlette
# wraps in reverse add-order) — it assigns the request ID and times
# the whole request/response cycle, CORS handling included, and every
# log line emitted anywhere while handling this request (rate_limit,
# chat.service, sync workers, ...) can be tied back to it.

from app.core.middleware import (
    RequestContextMiddleware,
)

app.add_middleware(RequestContextMiddleware)


# ---------------------------------
# Routers
# ---------------------------------

app.include_router(
    chat_router
)

app.include_router(
    images_router
)

app.include_router(
    media_router
)

app.include_router(
    stores_router
)

app.include_router(
    auth_router
)

app.include_router(
    api_keys_router
)

app.include_router(
    billing_router
)

app.include_router(
    admin_router
)

app.include_router(
    products_router
)

app.include_router(
    datasources_router
)

app.include_router(
    knowledge_router
)

# NOTE: discovery + mapping are mounted with an explicit "/v1"
# prefix since their own router prefixes are "/discovery" and
# "/mapping" (no version segment). Do NOT also include
# app.api.v1.chat, app.api.v1.products, or app.api.v1.connectors
# here — chat/products duplicate the routers above at the same
# paths, and connectors/test duplicates /v1/datasources/test
# without tenant auth. See app/ARCHITECTURE_CLEANUP.md.
app.include_router(
    discovery_v1_router,
    prefix="/v1",
)

app.include_router(
    mapping_router,
    prefix="/v1",
)

# Served at bare "/widget.js" (no /v1 prefix) — this is the URL
# merchants paste into a <script src="..."> tag on their own site.
app.include_router(
    widget_router
)

# Customer-facing full-page chat UI (frontend/chat/).
# Served at /chat/ so DEPLOY.md links work: /chat/?key=pk_live_...
from pathlib import Path as _Path
from fastapi.staticfiles import StaticFiles
_CHAT_DIR = _Path(__file__).resolve().parent.parent / "frontend" / "chat"
if _CHAT_DIR.is_dir():
    app.mount("/chat", StaticFiles(directory=str(_CHAT_DIR), html=True), name="chat-ui")


# ---------------------------------
# Error handling
# ---------------------------------
#
# Clients never receive internal stack traces. Full
# diagnostics go to server-side logs only. Every error response
# carries the same request_id that's in the structured logs and in
# the X-Request-ID response header, so a merchant reporting "chat
# broke around 3pm" gives you something to grep for immediately.

import asyncio

from app.core.alerting import send_alert
from app.core.request_context import get_request_id


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request,
    exc: StarletteHTTPException,
):

    headers = dict(getattr(exc, "headers", None) or {})
    headers["X-Request-ID"] = get_request_id() or "-"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": get_request_id(),
        },
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request,
    exc: RequestValidationError,
):

    return JSONResponse(
        status_code=422,
        content={
            "detail": (
                "Invalid request payload."
            ),
            "request_id": get_request_id(),
            "errors": [
                {
                    "loc": list(
                        error.get(
                            "loc",
                            [],
                        )
                    ),
                    "msg": error.get(
                        "msg",
                        "",
                    ),
                    "type": error.get(
                        "type",
                        "",
                    ),
                }
                for error in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request,
    exc: Exception,
):

    request_id = get_request_id()

    logger.exception(
        "Unhandled error on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        extra={
            "http_method": request.method,
            "path": request.url.path,
        },
    )

    # Fire-and-forget: an unhandled 500 is exactly the kind of event
    # that should page someone, not just sit in a log file waiting
    # to be grepped after a merchant complains. Scheduled as a
    # background task so a slow/down webhook never adds latency to
    # the error response itself.
    asyncio.create_task(
        send_alert(
            title="Unhandled exception",
            detail=f"{type(exc).__name__}: {exc}",
            extra={
                "path": request.url.path,
                "method": request.method,
            },
        )
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "Internal server error."
            ),
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id or "-"},
    )


# ---------------------------------
# Health
# ---------------------------------

@app.get(
    "/health",
    tags=["Health"],
)
async def health():

    return {
        "status": "ok"
    }


@app.get(
    "/ready",
    tags=["Health"],
)
async def readiness():
    """Verify dependencies required to serve authenticated traffic."""

    import asyncio
    from sqlalchemy import text
    from app.core.redis import redis_client

    try:
        await asyncio.to_thread(_check_database_readiness, text("SELECT 1"))
        await redis_client.ping()
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready"},
        )

    return {"status": "ready"}


def _check_database_readiness(query):
    with engine.connect() as connection:
        connection.execute(query)