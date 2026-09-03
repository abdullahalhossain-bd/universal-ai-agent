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

from app.core.config import settings
from app.core.logging_config import configure_logging
configure_logging(json_logs=settings.log_json)
logger = logging.getLogger("app")

from app.db.database import Base, engine
from app.db.models import Store, APIKey, Product, DataSource, ChatImage, User, PlatformAdmin
from app.chat.models import ChatSession, ChatMessage
from app.knowledge.chunk import KnowledgePage, KnowledgeChunk
from app.usage.models import UsageRecord

from app.api.routes.products import router as products_router
from app.api.routes.datasources import router as datasources_router
from app.api.routes.stores import router as stores_router
from app.api.v1.knowledge import router as knowledge_router
from app.chat.router import router as chat_router
from app.api.routes.messages import router as messages_router
from app.api.routes.images import router as images_router
from app.api.routes.media import router as media_router
from app.api.v1.discovery import router as discovery_v1_router
from app.api.v1.mapping import router as mapping_v1_router
from app.widget.router import router as widget_router
from app.api.routes.auth import router as auth_router
from app.api.routes.api_keys import router as api_keys_router
from app.api.routes.billing import router as billing_router
from app.api.routes.admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.knowledge.vector_support import resolve_vector_support
    if resolve_vector_support(engine):
        logger.info("pgvector detected: knowledge embeddings enabled")
    else:
        logger.warning("pgvector unavailable: knowledge_chunks.embedding falls back to Text; semantic search disabled")
    if settings.auto_create_tables:
        if settings.environment.lower() in ("production", "prod"):
            raise RuntimeError("auto_create_tables=true with environment=production. Set AUTO_CREATE_TABLES=false and run `alembic upgrade head` as a deploy step instead — see alembic/README.md.")
        Base.metadata.create_all(bind=engine)
    else:
        logger.info("auto_create_tables=false: skipping schema creation; run `alembic upgrade head` to manage the schema")
    yield


app = FastAPI(title="Universal Commerce AI API", version="1.0.0", lifespan=lifespan)

from app.core.security import get_cors_allow_origins
app.add_middleware(CORSMiddleware, allow_origins=get_cors_allow_origins(), allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["x-api-key", "content-type", "authorization"])

from app.core.middleware import RequestContextMiddleware
app.add_middleware(RequestContextMiddleware)

app.include_router(chat_router)
app.include_router(messages_router)
app.include_router(images_router)
app.include_router(media_router)
app.include_router(stores_router)
app.include_router(auth_router)
app.include_router(api_keys_router)
app.include_router(billing_router)
app.include_router(admin_router)
app.include_router(products_router)
app.include_router(datasources_router)
app.include_router(knowledge_router)
app.include_router(discovery_v1_router, prefix="/v1")
app.include_router(mapping_v1_router, prefix="/v1")
app.include_router(widget_router)

from pathlib import Path as _Path
from fastapi.staticfiles import StaticFiles
_CHAT_DIR = _Path(__file__).resolve().parent.parent / "frontend" / "chat"
if _CHAT_DIR.is_dir():
    app.mount("/chat", StaticFiles(directory=str(_CHAT_DIR), html=True), name="chat-ui")

import asyncio
from app.core.alerting import send_alert
from app.core.request_context import get_request_id

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    headers = dict(getattr(exc, "headers", None) or {})
    headers["X-Request-ID"] = get_request_id() or "-"
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "request_id": get_request_id()}, headers=headers)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "Invalid request payload.", "request_id": get_request_id(), "errors": [{"loc": list(error.get("loc", [])), "msg": error.get("msg", ""), "type": error.get("type", "")} for error in exc.errors()]})

@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    request_id = get_request_id()
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc, extra={"http_method": request.method, "path": request.url.path})
    asyncio.create_task(send_alert(title="Unhandled exception", detail=f"{type(exc).__name__}: {exc}", extra={"path": request.url.path, "method": request.method}))
    return JSONResponse(status_code=500, content={"detail": "Internal server error.", "request_id": request_id}, headers={"X-Request-ID": request_id or "-"})

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}

@app.get("/ready", tags=["Health"])
async def readiness():
    import asyncio
    from sqlalchemy import text
    from app.core.redis import redis_client
    try:
        await asyncio.to_thread(_check_database_readiness, text("SELECT 1"))
        await redis_client.ping()
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}


def _check_database_readiness(query):
    with engine.connect() as connection:
        connection.execute(query)
