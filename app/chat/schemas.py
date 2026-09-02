from pydantic import BaseModel, Field


class ChatRequest(BaseModel):

    message: str = Field(
        min_length=1,
        max_length=2000,
    )

    conversation_id: str | None = None


class ChatResponse(BaseModel):

    conversation_id: str

    type: str

    message: str

    products: list[dict] = []

    sources: list[dict] = []


class ImageUploadResponse(BaseModel):

    image_id: str

    url: str

    mime_type: str

    size: int


class ImageAnalyzeRequest(BaseModel):

    conversation_id: str | None = None

    # If provided, the image is treated as a visual question
    # ("is this available in blue?") instead of a product-match
    # search.
    question: str | None = Field(
        default=None,
        max_length=500,
    )


class ImageChatResponse(BaseModel):

    conversation_id: str

    type: str

    message: str

    products: list[dict] = []

    sources: list[dict] = []

    analysis: dict | None = None