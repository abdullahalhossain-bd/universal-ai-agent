"""
Image upload API for image chat.

Accepts a multipart file upload, validates it (real magic-byte
sniffing), stores it via the process-wide ObjectStorage backend, and
persists a ChatImage row so the returned image_id can later be resolved.
"""

from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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


@router.post("")
async def upload_image(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    api_key: APIKey = Depends(authenticate_api_key),
    db: Session = Depends(get_db),
):
    store = resolve_active_store(api_key=api_key, db=db)
    require_feature(store, FEATURE_IMAGE_SEARCH)

    if conversation_id:
        foreign_session = (
            db.query(ChatSession)
            .filter(
                ChatSession.conversation_key == conversation_id,
                ChatSession.store_id != store.id,
            )
            .first()
        )
        if foreign_session is not None:
            raise HTTPException(status_code=404, detail="Conversation not found")

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
            conversation_id=conversation_id,
        )
    except Exception:
        db.rollback()
        try:
            await storage.delete(storage_key)
        except Exception:
            pass
        raise

    url = await storage.get_url(storage_key)
    return {
        "image_id": image_record.id,
        "url": url,
        "mime_type": image_record.mime_type,
        "size": image_record.size,
    }


@router.post("/{image_id}/analyze", response_model=ImageChatResponse)
async def analyze_image(
    image_id: str,
    request: ImageAnalyzeRequest,
    api_key: APIKey = Depends(authenticate_api_key),
    db: Session = Depends(get_db),
):
    store = resolve_active_store(api_key=api_key, db=db)
    require_feature(store, FEATURE_IMAGE_SEARCH)

    # Image IDs are store-scoped, and conversation-bound uploads must also
    # remain bound to their original conversation. Without this check a
    # caller who knows an image_id could attach an uploaded image to a
    # different conversation in the same store.
    image_record = ImageRepository(db).get(store_id=store.id, image_id=image_id)
    if image_record is None:
        raise HTTPException(status_code=404, detail="Image not found")
    if image_record.conversation_id is not None and image_record.conversation_id != request.conversation_id:
        raise HTTPException(status_code=404, detail="Image not found")

    service = ChatService(db=db)
    return await service.handle_image(
        store=store,
        image_id=image_id,
        conversation_id=request.conversation_id,
        question=request.question,
    )
