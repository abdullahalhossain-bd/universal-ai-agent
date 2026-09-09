"""FastAPI application entrypoint."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import settings
from app.core.logging_config import configure_logging
configure_logging(json_logs=settings.log_json)
logger=logging.getLogger("app")
from app.db.database import Base,engine
from app.db.models import Store,APIKey,Product,DataSource,ChatImage,User,PlatformAdmin,SyncRun
from app.db.admin_audit import AdminAuditLog
from app.db.agent_config import AgentConfig
from app.db.visitor import VisitorProfile
from app.chat.models import ChatSession,ChatMessage
from app.knowledge.chunk import KnowledgePage,KnowledgeChunk
from app.usage.models import UsageRecord
from app.api.routes.products import router as products_router
from app.api.routes.datasources import router as datasources_router
from app.api.routes.stores import router as stores_router
from app.api.v1.knowledge import router as knowledge_router
from app.chat.router import router as chat_router
from app.api.routes.messages import router as messages_router
from app.api.routes.images import router as images_router
from app.api.routes.media import router as media_router
from app.api.routes.behavior import router as behavior_router
from app.api.routes.analytics import router as analytics_router
from app.api.v1.discovery import router as discovery_v1_router
from app.api.v1.mapping import router as mapping_v1_router
from app.widget.router import router as widget_router
from app.api.routes.auth import router as auth_router
from app.api.routes.api_keys import router as api_keys_router
from app.api.routes.billing import router as billing_router
from app.api.routes.admin import router as admin_router
from app.api.routes.admin_analytics import router as admin_analytics_router

def _ensure_alembic_baseline():
    from sqlalchemy import inspect
    inspector=inspect(engine)
    if inspector.has_table("alembic_version"):return
    missing_tables=[t.name for t in Base.metadata.sorted_tables if not inspector.has_table(t.name)];missing_columns=[]
    for t in Base.metadata.sorted_tables:
        if not inspector.has_table(t.name):continue
        actual={c["name"] for c in inspector.get_columns(t.name)}
        for c in t.columns:
            if c.name not in actual:missing_columns.append(f"{t.name}.{c.name}")
    if missing_tables or missing_columns:
        details=[]
        if missing_tables:details.append(f"tables={missing_tables}")
        if missing_columns:details.append(f"columns={missing_columns}")
        raise RuntimeError("Alembic version table is missing and the existing schema does not match the active ORM schema; refusing to stamp head: "+"; ".join(details))
    from alembic import command
    from alembic.config import Config
    command.stamp(Config(str(Path(__file__).resolve().parent.parent/"alembic.ini")),"head")
@asynccontextmanager
async def lifespan(app:FastAPI):
    from app.knowledge.vector_support import resolve_vector_support
    if resolve_vector_support(engine):logger.info("pgvector detected: knowledge embeddings enabled")
    else:logger.warning("pgvector unavailable: knowledge_chunks.embedding falls back to Text; semantic search disabled")
    if settings.auto_create_tables:
        if settings.environment.lower() in("production","prod"):raise RuntimeError("auto_create_tables=true with environment=production. Set AUTO_CREATE_TABLES=false and run `alembic upgrade head` as a deploy step instead — see alembic/README.md.")
        Base.metadata.create_all(bind=engine)
    else:_ensure_alembic_baseline()
    background_tasks=[]
    if settings.run_sync_inline:
        try:
            from app.sync.worker import run_worker
            from app.sync.scheduler import scheduler as run_scheduler
            background_tasks += [asyncio.create_task(run_worker(),name="inline-sync-worker"),asyncio.create_task(run_scheduler(settings.redis_url),name="inline-sync-scheduler")]
        except Exception:logger.exception("Failed to start inline sync worker/scheduler")
    yield
    for task in background_tasks:task.cancel()
    for task in background_tasks:
        try:await task
        except(asyncio.CancelledError,Exception):pass
app=FastAPI(title="Universal Commerce AI API",version="1.0.0",lifespan=lifespan)
from app.core.security import get_cors_allow_origins
app.add_middleware(CORSMiddleware,allow_origins=get_cors_allow_origins(),allow_credentials=False,allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],allow_headers=["x-api-key","content-type","authorization"])
from app.core.middleware import RequestContextMiddleware
app.add_middleware(RequestContextMiddleware)
app.include_router(chat_router);app.include_router(messages_router);app.include_router(images_router);app.include_router(media_router);app.include_router(stores_router);app.include_router(auth_router);app.include_router(api_keys_router);app.include_router(billing_router);app.include_router(admin_router);app.include_router(admin_analytics_router);app.include_router(products_router);app.include_router(datasources_router);app.include_router(knowledge_router);app.include_router(behavior_router);app.include_router(analytics_router);app.include_router(discovery_v1_router,prefix="/v1");app.include_router(mapping_v1_router,prefix="/v1");app.include_router(widget_router)
_CHAT_DIR=Path(__file__).resolve().parent.parent/"frontend"/"chat"
if _CHAT_DIR.is_dir():app.mount("/chat",StaticFiles(directory=str(_CHAT_DIR),html=True),name="chat-ui")
_DASHBOARD_DIR=Path(__file__).resolve().parent.parent/"frontend"/"dashboard"
if _DASHBOARD_DIR.is_dir():app.mount("/dashboard",StaticFiles(directory=str(_DASHBOARD_DIR),html=True),name="dashboard-ui")
from app.core.alerting import send_alert
from app.core.request_context import get_request_id
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request,exc):
    headers=dict(getattr(exc,"headers",None) or {});headers["X-Request-ID"]=get_request_id() or "-";return JSONResponse(status_code=exc.status_code,content={"detail":exc.detail,"request_id":get_request_id()},headers=headers)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request,exc):return JSONResponse(status_code=422,content={"detail":"Invalid request payload.","request_id":get_request_id(),"errors":[{"loc":list(e.get("loc",[])),"msg":e.get("msg",""),"type":e.get("type","")} for e in exc.errors()]})
@app.exception_handler(Exception)
async def unhandled_exception_handler(request,exc):
    request_id=get_request_id();logger.exception("Unhandled error on %s %s: %s",request.method,request.url.path,exc,extra={"http_method":request.method,"path":request.url.path});asyncio.create_task(send_alert(title="Unhandled exception",detail=f"{type(exc).__name__}: {exc}",extra={"path":request.url.path,"method":request.method}));return JSONResponse(status_code=500,content={"detail":"Internal server error.","request_id":request_id},headers={"X-Request-ID":request_id or "-"})
@app.get("/",tags=["Health"])
async def root():return {"name":"Universal Commerce AI API","version":"1.0.0","status":"ok","docs":"/docs","health":"/health","ready":"/ready"}
@app.get("/health",tags=["Health"])
async def health():return {"status":"ok"}
@app.get("/ready",tags=["Health"])
async def readiness():
    from sqlalchemy import text
    from app.core.redis import redis_client
    try:await asyncio.to_thread(_check_database_readiness,text("SELECT 1"));await redis_client.ping()
    except Exception:return JSONResponse(status_code=503,content={"status":"not_ready"})
    return {"status":"ready"}
def _check_database_readiness(query):
    with engine.connect() as connection:connection.execute(query)
