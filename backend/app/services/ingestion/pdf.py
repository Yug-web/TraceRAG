import io
import json
import logging
import subprocess
import sys

from pypdf import PdfReader

from app.core.config import Settings
from app.core.errors import DocumentError


def extract_pages(data: bytes, max_pages: int, max_chars: int, max_stream_bytes: int) -> list[str]:
    """Only the worker invokes this on user input; tests can call it directly."""
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise DocumentError("encrypted_pdf", "Password-protected PDFs are not supported.")
        if len(reader.pages) > max_pages:
            raise DocumentError("too_many_pages", f"PDF exceeds the {max_pages}-page limit.")
        pages = []
        total = 0
        for page in reader.pages:
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > max_stream_bytes:
                raise DocumentError("complex_pdf", "A PDF page exceeds the processing limit.")
            text = (page.extract_text() or "").replace("\x00", "").replace("\r\n", "\n").strip()
            total += len(text)
            if total > max_chars:
                raise DocumentError("too_much_text", "PDF exceeds the extracted-text limit.")
            pages.append(text)
        if not any(text.strip() for text in pages):
            raise DocumentError("no_text", "No readable text found. Scanned PDFs require OCR.")
        return pages
    except DocumentError:
        raise
    except Exception as exc:
        # Parser exceptions can contain document data; expose a stable, safe message.
        raise DocumentError("invalid_pdf", "The PDF is malformed or cannot be read.") from exc


def parse_pdf(data: bytes, settings: Settings) -> list[str]:
    """A separate process can be terminated even if the parser becomes stuck."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.services.ingestion.worker",
                str(settings.max_pdf_pages),
                str(settings.max_text_chars),
                str(settings.max_page_stream_bytes),
            ],
            input=data,
            capture_output=True,
            timeout=settings.parse_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DocumentError("parse_timeout", "PDF processing timed out.") from exc
    if result.returncode != 0:
        raise DocumentError("parser_failed", "The PDF parser could not finish processing.")
    payload = json.loads(result.stdout)
    if "error" in payload:
        raise DocumentError(payload["error"], payload["message"])
    return payload["pages"]
