from fastapi import (
    APIRouter,
    Depends,
)

from sqlalchemy.orm import Session

from app.auth.api_key import (
    get_api_key,
)

from app.chat.schemas import (
    ChatRequest,
    ChatResponse,
)

from app.chat.service import (
    ChatService,
)

from app.db.database import (
    get_db,
)

from app.db.models import (
    APIKey,
)


router = APIRouter(
    prefix="/v1/chat",
    tags=["Chat"],
)


@router.post(
    "",
    response_model=ChatResponse,
)
async def chat(
    payload: ChatRequest,

    api_key: APIKey = Depends(
        get_api_key
    ),

    db: Session = Depends(
        get_db
    ),
):

    service = ChatService(
        db=db
    )

    return await service.handle(
        store_id=api_key.store_id,
        request=payload,
    )
