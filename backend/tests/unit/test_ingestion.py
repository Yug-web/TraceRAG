import subprocess

import pytest

from app.core.config import Settings
from app.core.errors import DocumentError
from app.services.ingestion.chunking import chunk_pages
from app.services.ingestion.documents import validate_filename
from app.services.ingestion.pdf import extract_pages, parse_pdf
from tests.pdf_factory import make_pdf


def test_chunks_cover_pages_without_crossing_boundaries():
    pages = ["abcdefghijk", "", "second page"]
    chunks = chunk_pages(pages, size=5, overlap=2)
    for page_number in (1, 3):
        covered = set()
        for chunk in chunks:
            if chunk.page_number == page_number:
                assert chunk.text == pages[page_number - 1][chunk.start_char : chunk.end_char]
                assert len(chunk.text) <= 5
                covered.update(range(chunk.start_char, chunk.end_char))
        assert covered == set(range(len(pages[page_number - 1])))
    assert not any(chunk.page_number == 2 for chunk in chunks)


@pytest.mark.parametrize("size,overlap", [(0, 0), (5, 5), (5, -1)])
def test_invalid_chunk_configuration(size, overlap):
    with pytest.raises(ValueError):
        chunk_pages(["text"], size, overlap)


@pytest.mark.parametrize("name", ["../secret.pdf", "C:\\secret.pdf", "a/b.pdf", "a\x00.pdf"])
def test_paths_and_control_characters_rejected(name):
    with pytest.raises(DocumentError, match="plain filename"):
        validate_filename(name)


def test_extraction_preserves_blank_page_numbers():
    assert extract_pages(make_pdf(["First page", "", "Third page"]), 10, 1000, 10000) == [
        "First page",
        "",
        "Third page",
    ]


@pytest.mark.parametrize(
    "data,code",
    [
        (b"%PDF-1.7\nbroken", "invalid_pdf"),
        (make_pdf([""]), "no_text"),
        (make_pdf(["secret"], password="password"), "encrypted_pdf"),
        (make_pdf(["one", "two"]), "too_many_pages"),
    ],
)
def test_unreadable_and_oversized_page_sets(data, code):
    with pytest.raises(DocumentError) as error:
        extract_pages(data, 1, 1000, 10000)
    assert error.value.code == code


def test_extracted_text_limit():
    with pytest.raises(DocumentError) as error:
        extract_pages(make_pdf(["long text"]), 10, 3, 10000)
    assert error.value.code == "too_much_text"


def test_page_stream_limit():
    with pytest.raises(DocumentError) as error:
        extract_pages(make_pdf(["text"]), 10, 1000, 1)
    assert error.value.code == "complex_pdf"


def test_parser_deadline_is_reported(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("worker", kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(DocumentError) as error:
        parse_pdf(b"%PDF-", Settings(_env_file=None))
    assert error.value.code == "parse_timeout"


def test_real_worker_extracts_synthetic_pdf():
    assert parse_pdf(make_pdf(["Worker test"]), Settings(_env_file=None)) == ["Worker test"]
