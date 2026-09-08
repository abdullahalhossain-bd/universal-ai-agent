from fastapi import APIRouter

from app.api.v1.chat import (
    router as chat_router,
)

from app.api.v1.connectors import (
    router as connector_router,
)

from app.api.v1.discovery import (
    router as discovery_router,
)

from app.api.v1.mapping import (
    router as mapping_router,
)

from app.api.v1.products import (
    router as product_router,
)

from app.api.v1.knowledge import (
    router as knowledge_router,
)


router = APIRouter()


router.include_router(
    chat_router
)

router.include_router(
    discovery_router
)

router.include_router(
    mapping_router
)

router.include_router(
    connector_router
)

router.include_router(
    product_router
)

router.include_router(
    knowledge_router
)