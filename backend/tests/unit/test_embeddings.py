import math

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import DocumentError
from app.schemas.search import SearchRequest
from app.services.embeddings.encoder import EmbeddingProfile, LocalEncoder, normalize
from app.services.embeddings.indexing import encode_checked


@pytest.mark.parametrize("vector", [[0, 0], [1], [math.nan, 1], [math.inf, 1]])
def test_invalid_vectors_are_rejected(vector):
    with pytest.raises(ValueError):
        normalize(vector, 2)


def test_normalization():
    assert normalize([3, 4], 2) == [0.6, 0.8]


def test_profile_identity_includes_preprocessing_and_revision():
    first = EmbeddingProfile("model", "a" * 40, 384, 256)
    assert first.id == EmbeddingProfile("model", "a" * 40, 384, 256).id
    assert first.id != EmbeddingProfile("model", "b" * 40, 384, 256).id
    assert first.id != EmbeddingProfile("model", "a" * 40, 384, 128).id
    assert first.id != EmbeddingProfile("model", "a" * 40, 384, 256, "other").id


def test_model_is_lazy_and_failures_are_safe(monkeypatch, caplog):
    encoder = LocalEncoder(Settings(_env_file=None))
    assert encoder._model is None

    def fail(texts):
        raise RuntimeError("private query or local credential")

    monkeypatch.setattr(encoder, "_encode", fail)
    with pytest.raises(DocumentError) as error:
        encoder.encode(["query"])
    assert error.value.status_code == 503
    assert "private query" not in str(error.value)
    assert "private query" not in caplog.text


def test_encoder_must_return_one_vector_per_input():
    class BrokenEncoder:
        profile = EmbeddingProfile("fake", "a" * 40, 2, 256)

        def encode(self, texts):
            return []

    with pytest.raises(DocumentError):
        encode_checked(BrokenEncoder(), ["text"])


@pytest.mark.parametrize(
    "body",
    [
        {"query": ""},
        {"query": " \n "},
        {"query": "a" * 2001},
        {"query": "q", "top_k": 0},
        {"query": "q", "top_k": 21},
        {"query": "q", "top_k": True},
        {"query": "q", "top_k": 1.5},
    ],
)
def test_search_validation(body):
    with pytest.raises(ValidationError):
        SearchRequest(**body)


def test_query_is_trimmed():
    assert SearchRequest(query="  evidence  ").query == "evidence"
