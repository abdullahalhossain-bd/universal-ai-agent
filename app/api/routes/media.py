"""
Serves files written by `app.images.local_storage.LocalObjectStorage`.

`LocalObjectStorage.get_url()` returns paths of the form
`/local-media/{key}` (key = `{store_id}/{uuid}.{ext}`) — this router
is what actually serves that path. No `/v1` prefix and no API-key
auth, same reasoning as `app.widget.router`'s `/widget.js`: uploaded
chat-image URLs get embedded directly in `<img src>` tags in the
merchant-facing chat widget, which can't attach an `x-api-key`
header to an image request.

Path-traversal is blocked by resolving the requested file against
`settings.image_storage_path` and rejecting anything that resolves
outside of it — the key itself is server-generated
(store_id/uuid.ext) and never contains `..`, but this stays
defensive in case a future caller ever passes a client-influenced
key through.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings


router = APIRouter(tags=["Media"])


@router.get("/local-media/{key:path}")
async def local_media(key: str):

    base_dir = Path(settings.image_storage_path).resolve()
    requested = (base_dir / key).resolve()

    if base_dir not in requested.parents and requested != base_dir:
        raise HTTPException(status_code=404, detail="Not found")

    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(
        requested,
        headers={
            # Uploaded chat images are immutable once stored (a new
            # upload always gets a new uuid-based key), so this is
            # safe to cache aggressively at the edge/browser.
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
