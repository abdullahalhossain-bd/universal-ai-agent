"""
Image upload API for image chat.

Accepts a multipart file upload, validates it (real magic-byte
sniffing — see `app.images.validation.sniff_image_mime` — never
trusts the client-declared Content-Type), stores it via the
process-wide `ObjectStorage` backend, and persists a `ChatImage` row
so the returned `image_id` can later be resolved by
`ChatService.handle_image` / `ImageAnalysisTool` (both look it up
through `app.images.repository.ImageRepository`, store-scoped).

Deliberately mirrors `app.chat.router`'s auth pattern
(`authenticate_api_key` + manual `Store` lookup) rather than
`app.core.tenant.get_current_store`, since this is part of the same
image-chat feature family as `POST /v1/chat`.
"""

from __future__ import annotations

import io
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from sqlalchemy.orm import Session

from app.auth.dependency import authenticate_api_key, resolve_active_store
from app.auth.models import APIKey

from app.db.database import get_db

from app.core.features import FEATURE_IMAGE_SEARCH, require_feature

from app.chat.schemas import (
    ImageAnalyzeRequest,
    ImageChatResponse,
)
from app.chat.service import ChatService

from app.images.hashing import compute_image_hash
from app.images.repository import ImageRepository
from app.images.storage import get_object_storage
from app.images.validation import (
    MAX_FILE_SIZE_BYTES,
    sniff_image_mime,
    validate_image,
)


router = APIRouter(
    prefix="/v1/images",
    tags=["Images"],
)


@router.post("")
async def upload_image(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),

    api_key: APIKey = Depends(authenticate_api_key),
    db: Session = Depends(get_db),
):

    store = resolve_active_store(api_key=api_key, db=db)

    require_feature(store, FEATURE_IMAGE_SEARCH)

    # Read the whole upload up front: hashing, mime-sniffing, and the
    # size check below all need the full bytes anyway, and 10 MB (the
    # validation ceiling) is small enough to hold in memory safely.
    raw_bytes = await file.read()

    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")

    # The client-declared Content-Type is just a label — verify what
    # the bytes actually are before they ever reach storage.
    sniffed_mime = sniff_image_mime(raw_bytes)

    if sniffed_mime is None:
        raise HTTPException(
            status_code=400,
            detail="Unsupported or unrecognized image type",
        )

    try:
        validate_image(mime_type=sniffed_mime, size=len(raw_bytes))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    image_hash = compute_image_hash(raw_bytes)

    extension = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }[sniffed_mime]

    storage_key = f"{store.id}/{uuid.uuid4()}.{extension}"

    storage = get_object_storage()

    await storage.upload(
        io.BytesIO(raw_bytes),
        storage_key,
    )

    image_record = ImageRepository(db).create(
        store_id=store.id,
        storage_key=storage_key,
        mime_type=sniffed_mime,
        size=len(raw_bytes),
        image_hash=image_hash,
        conversation_id=conversation_id,
    )

    url = await storage.get_url(storage_key)

    return {
        "image_id": image_record.id,
        "url": url,
        "mime_type": image_record.mime_type,
        "size": image_record.size,
    }


@router.post(
    "/{image_id}/analyze",
    response_model=ImageChatResponse,
)
async def analyze_image(
    image_id: str,
    request: ImageAnalyzeRequest,

    api_key: APIKey = Depends(authenticate_api_key),
    db: Session = Depends(get_db),
):
    """
    Runs vision analysis (product match or visual Q&A, depending on
    whether `question` is set) on a previously uploaded image and
    returns an assistant turn in the same shape as `POST /v1/chat`.

    This is the second half of the image-chat flow started by
    `POST /v1/images`: the client uploads the file there to get an
    `image_id`, then calls this endpoint to actually run the model
    on it. Split into two calls so the same uploaded image can be
    re-analyzed with a different follow-up question without
    re-uploading the bytes.

    Wires up `ChatService.handle_image` / `VisionService`, which
    already existed but had no route pointing at them.
    """

    store = resolve_active_store(api_key=api_key, db=db)

    require_feature(store, FEATURE_IMAGE_SEARCH)

    service = ChatService(db=db)

    return await service.handle_image(
        store=store,
        image_id=image_id,
        conversation_id=request.conversation_id,
        question=request.question,
    )