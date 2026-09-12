"""
Image upload API for image chat.

Accepts a multipart file upload, validates it (real magic-byte
sniffing), stores it via the process-wide ObjectStorage backend, and
persists a ChatImage row so the returned image_id can later be resolved.
"""

from __future__ import annotations

import hmac
import io
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependency import authenticate_api_key, resolve_active_store
from app.auth.models import APIKey
from app.chat.models import ChatSession
from app.chat.schemas import ImageAnalyzeRequest, ImageChatResponse
from app.chat.service import ChatService
from app.core.features import FEATURE_IMAGE_SEARCH, require_feature
from app.db.database import get_db
from app.images.hashing import compute_image_hash
from app.images.repository import ImageRepository
from app.images.storage import get_object_storage
from app.images.validation import MAX_FILE_SIZE_BYTES, sniff_image_mime, validate_image

router = APIRouter(prefix="/v1/images", tags=["Images"])


def _verify_conversation_access(db: Session, store_id: str, conversation_id: str | None, conversation_token: str | None) -> ChatSession | None:
    if not conversation_id:
        return None
    session = db.query(ChatSession).filter(ChatSession.store_id == store_id, ChatSession.conversation_key == conversation_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not conversation_token:
        raise HTTPException(status_code=401, detail="Conversation token required")
    expected = str(session.access_token or "")
    if not expected or not hmac.compare_digest(expected, conversation_token):
        raise HTTPException(status_code=403, detail="Invalid conversation token")
    return session


@router.post("")
async def upload_image(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    x_conversation_token: str | None = Header(default=None, alias="x-conversation-token"),
    api_key: APIKey = Depends(authenticate_api_key),
    db: Session = Depends(get_db),
):
    store = resolve_active_store(api_key=api_key, db=db)
    require_feature(store, FEATURE_IMAGE_SEARCH)

    # The browser widget historically submitted conversation_id in the
    # multipart form but could not attach the conversation token to this
    # request. Keep the upload endpoint backward-compatible without
    # weakening conversation security: when a token is present, verify and
    # bind the image to that conversation; when it is absent, upload the
    # image as an unbound image and require the token later at /analyze.
    # This also prevents an untrusted caller from attaching an image to an
    # arbitrary conversation merely by knowing its public conversation id.
    verified_session = None
    persisted_conversation_id = None
    if conversation_id and x_conversation_token:
        verified_session = _verify_conversation_access(
            db, store.id, conversation_id, x_conversation_token
        )
        persisted_conversation_id = verified_session.conversation_key

    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    sniffed_mime = sniff_image_mime(raw_bytes)
    if sniffed_mime is None:
        raise HTTPException(status_code=400, detail="Unsupported or unrecognized image type")
    try:
        validate_image(mime_type=sniffed_mime, size=len(raw_bytes))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    image_hash = compute_image_hash(raw_bytes)
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[sniffed_mime]
    storage_key = f"{store.id}/{uuid.uuid4()}.{extension}"
    storage = get_object_storage()
    await storage.upload(io.BytesIO(raw_bytes), storage_key)
    try:
        image_record = ImageRepository(db).create(
            store_id=store.id,
            storage_key=storage_key,
            mime_type=sniffed_mime,
            size=len(raw_bytes),
            image_hash=image_hash,
            conversation_id=persisted_conversation_id,
        )
    except Exception:
        db.rollback()
        try:
            await storage.delete(storage_key)
        except Exception:
            pass
        raise

    url = await storage.get_url(storage_key)
    return {"image_id": image_record.id, "url": url, "mime_type": image_record.mime_type, "size": image_record.size}


@router.post("/{image_id}/analyze", response_model=ImageChatResponse)
async def analyze_image(
    image_id: str,
    request: ImageAnalyzeRequest,
    x_conversation_token: str | None = Header(default=None, alias="x-conversation-token"),
    api_key: APIKey = Depends(authenticate_api_key),
    db: Session = Depends(get_db),
):
    store = resolve_active_store(api_key=api_key, db=db)
    require_feature(store, FEATURE_IMAGE_SEARCH)
    image_record = ImageRepository(db).get(store_id=store.id, image_id=image_id)
    if image_record is None:
        raise HTTPException(status_code=404, detail="Image not found")
    if image_record.conversation_id is not None and image_record.conversation_id != request.conversation_id:
        raise HTTPException(status_code=404, detail="Image not found")

    _verify_conversation_access(db, store.id, request.conversation_id, x_conversation_token)

    service = ChatService(db=db)
    result = await service.handle_image(store=store, image_id=image_id, conversation_id=request.conversation_id, question=request.question)
    session = db.query(ChatSession).filter(ChatSession.store_id == store.id, ChatSession.conversation_key == result.get("conversation_id")).first()
    if session is not None:
        result["conversation_token"] = session.access_token
    return result
