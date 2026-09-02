def chunk_text(
    text: str,
    chunk_size: int = 700,
    overlap: int = 80,
):

    words = text.split()

    chunks = []

    start = 0

    while start < len(words):

        end = start + chunk_size

        chunk_words = words[start:end]

        chunks.append(
            " ".join(chunk_words)
        )

        start = end - overlap

        if start < 0:
            start = 0

        if end >= len(words):
            break

    return chunks
