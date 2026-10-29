import hashlib
import json
import logging
import math
import threading
from dataclasses import asdict, dataclass
from typing import Protocol

from app.core.config import Settings
from app.core.errors import DocumentError


@dataclass(frozen=True)
class EmbeddingProfile:
    model_name: str
    revision: str
    dimensions: int
    max_tokens: int
    preprocessing: str = "token-window-weighted-mean-l2-v1"

    @property
    def id(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_settings(cls, settings: Settings) -> "EmbeddingProfile":
        return cls(
            settings.embedding_model,
            settings.embedding_revision,
            settings.embedding_dimensions,
            settings.embedding_max_tokens,
        )


class Encoder(Protocol):
    profile: EmbeddingProfile

    def encode(self, texts: list[str]) -> list[list[float]]: ...


def normalize(vector: list[float], dimensions: int) -> list[float]:
    if len(vector) != dimensions or not all(math.isfinite(value) for value in vector):
        raise ValueError("Embedding dimensions or values are invalid")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm <= 1e-12:
        raise ValueError("Embedding has zero or invalid norm")
    return [value / norm for value in vector]


def tokenize_windows(tokenizer, text: str, max_tokens: int):
    encoded = tokenizer(
        text,
        truncation=True,
        max_length=max_tokens,
        stride=0,
        return_overflowing_tokens=True,
        return_special_tokens_mask=True,
    )
    features = [
        {name: encoded[name][index] for name in tokenizer.model_input_names if name in encoded}
        for index in range(len(encoded["input_ids"]))
    ]
    weights = [sum(value == 0 for value in mask) for mask in encoded["special_tokens_mask"]]
    if not features or not all(weight > 0 for weight in weights):
        raise ValueError("Require nonempty content-token windows")
    return features, weights


class LocalEncoder:
    """One lazily loaded CPU model, serialized across requests to bound inference memory."""

    def __init__(self, settings: Settings):
        self.profile = EmbeddingProfile.from_settings(settings)
        self.batch_size = settings.embedding_batch_size
        self.local_only = settings.embedding_local_files_only
        self._model = None
        self._lock = threading.Lock()

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            with self._lock:
                return self._encode(texts)
        except Exception as exc:
            logging.getLogger(__name__).error("Embedding operation failed: %s", type(exc).__name__)
            raise DocumentError(
                "embedding_unavailable", "The embedding model is unavailable.", 503
            ) from None

    def _encode(self, texts: list[str]) -> list[list[float]]:
        import torch
        from sentence_transformers import SentenceTransformer

        if self._model is None:
            model = SentenceTransformer(
                self.profile.model_name,
                revision=self.profile.revision,
                device="cpu",
                trust_remote_code=False,
                local_files_only=self.local_only,
                model_kwargs={"use_safetensors": True},
            )
            if model.get_embedding_dimension() != self.profile.dimensions:
                raise ValueError("Configured dimension does not match the model")
            if self.profile.max_tokens > model.max_seq_length:
                raise ValueError("Configured token limit exceeds the model's supported length")
            model.eval()
            self._model = model
        model = self._model
        tokenizer = model.tokenizer
        results = []
        for text in texts:
            # Overflow retains every token; no decode/re-tokenize step or silent tail truncation.
            windows, weights = tokenize_windows(tokenizer, text, self.profile.max_tokens)
            pooled = [0.0] * self.profile.dimensions
            for start in range(0, len(windows), self.batch_size):
                batch = windows[start : start + self.batch_size]
                features = tokenizer.pad(batch, padding=True, return_tensors="pt")
                with torch.inference_mode():
                    vectors = model(dict(features))["sentence_embedding"].cpu().tolist()
                for weight, vector in zip(
                    weights[start : start + self.batch_size], vectors, strict=True
                ):
                    normalized = normalize(vector, self.profile.dimensions)
                    for index, value in enumerate(normalized):
                        pooled[index] += value * weight
            results.append(normalize(pooled, self.profile.dimensions))
        return results
