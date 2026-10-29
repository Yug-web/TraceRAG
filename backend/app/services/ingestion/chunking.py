from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    page_number: int
    start_char: int
    end_char: int
    text: str


def chunk_pages(pages: list[str], size: int, overlap: int) -> list[TextChunk]:
    """Character windows stay on one page; offsets refer to normalized page text."""
    if size < 1 or not 0 <= overlap < size:
        raise ValueError("Require size > 0 and 0 <= overlap < size")
    chunks = []
    for page_number, text in enumerate(pages, start=1):
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if text[start:end].strip():
                chunks.append(TextChunk(page_number, start, end, text[start:end]))
            if end == len(text):
                break
            start = end - overlap
    return chunks
