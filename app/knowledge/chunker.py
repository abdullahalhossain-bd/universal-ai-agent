"""
Text chunking for the knowledge subsystem.

Exposes:
    - `chunk_text(text, chunk_size, overlap)` (module-level function)
    - `TextChunker` (class wrapper around `chunk_text`, used by
      `KnowledgeService.ingest`)
"""


def chunk_text(
    text: str,
    chunk_size: int = 1200,
    overlap: int = 200,
):
    """
    Split `text` into overlapping chunks of approximately `chunk_size`
    words, with `overlap` words of overlap between consecutive chunks.
    """

    if not text:
        return []

    words = text.split()

    chunks = []

    start = 0

    while start < len(words):
        end = start + chunk_size

        chunk = " ".join(words[start:end])

        if chunk:
            chunks.append(chunk)

        # No more words to consume — stop to avoid an infinite loop
        # when overlap >= chunk_size.
        if end >= len(words):
            break

        start = end - overlap

        if start < 0:
            start = 0

    return chunks


class TextChunker:
    """
    Thin object wrapper around `chunk_text` so callers can hold a chunker
    instance (e.g. inject it as a dependency or override defaults).
    """

    def __init__(
        self,
        chunk_size: int = 1200,
        overlap: int = 200,
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(
        self,
        text: str,
    ) -> list[str]:
        return chunk_text(
            text,
            chunk_size=self.chunk_size,
            overlap=self.overlap,
        )
