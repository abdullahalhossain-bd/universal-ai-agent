"""
Text chunking for the knowledge subsystem.

Exposes:
    - `chunk_text(text, chunk_size, overlap)` (module-level function)
    - `TextChunker` (class wrapper around `chunk_text`)
"""


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200):
    """Split text into bounded overlapping word chunks."""
    if not text or not str(text).strip():
        return []
    try:
        chunk_size = int(chunk_size)
        overlap = int(overlap)
    except (TypeError, ValueError) as exc:
        raise ValueError("chunk_size and overlap must be integers") from exc
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    words = str(text).split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = end - overlap
    return chunks


class TextChunker:
    """Configurable object wrapper around :func:`chunk_text`."""

    def __init__(self, chunk_size: int = 1200, overlap: int = 200):
        if int(chunk_size) <= 0 or int(overlap) < 0 or int(overlap) >= int(chunk_size):
            raise ValueError("overlap must be >= 0 and smaller than chunk_size; chunk_size must be positive")
        self.chunk_size = int(chunk_size)
        self.overlap = int(overlap)

    def split(self, text: str) -> list[str]:
        return chunk_text(text, chunk_size=self.chunk_size, overlap=self.overlap)
