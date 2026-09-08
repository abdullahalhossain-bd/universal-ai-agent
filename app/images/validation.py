ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_image(
    mime_type: str,
    size: int,
):

    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            "Unsupported image type"
        )

    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            "Image too large"
        )

    if size <= 0:
        raise ValueError(
            "Empty file"
        )

    return True


def sniff_image_mime(file_bytes: bytes) -> str | None:
    """
    Identify the real image format from its magic bytes.

    A client-declared `Content-Type` (or filename extension) is
    just a label the caller chose — it is not proof of what the
    bytes actually are. This checks the handful of byte signatures
    for the formats we accept and returns None for anything else,
    so the upload endpoint can reject a mislabeled or non-image
    file before it ever reaches storage or a vision model.
    """

    if file_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"

    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"

    if (
        file_bytes[:4] == b"RIFF"
        and file_bytes[8:12] == b"WEBP"
    ):
        return "image/webp"

    return None