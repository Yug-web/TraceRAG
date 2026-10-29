import math
import os

import pytest

from app.core.config import Settings
from app.services.embeddings.encoder import LocalEncoder, tokenize_windows


@pytest.mark.skipif(
    os.environ.get("TRACERAG_REAL_MODEL_TESTS") != "1",
    reason="Opt-in model download: set TRACERAG_REAL_MODEL_TESTS=1",
)
def test_real_model_dimensions_normalization_and_repeatability():
    encoder = LocalEncoder(Settings(_env_file=None))
    texts = [
        "Ocean currents transport heat.",
        "Plants use sunlight for photosynthesis.",
        "A long source passage. " * 200 + "The final sentence must also be encoded.",
    ]
    vectors = encoder.encode(texts)
    assert len(vectors) == 3
    for vector in vectors:
        assert len(vector) == 384
        assert all(math.isfinite(value) for value in vector)
        assert sum(value * value for value in vector) == pytest.approx(1, abs=1e-5)
    assert encoder.encode([texts[0]])[0] == pytest.approx(vectors[0], abs=1e-6)
    assert vectors[0] != pytest.approx(vectors[1], abs=1e-6)
    tokenizer = encoder._model.tokenizer
    windows, weights = tokenize_windows(tokenizer, texts[2], 256)
    assert len(windows) > 1
    assert all(len(window["input_ids"]) <= 256 for window in windows)
    assert sum(weights) == len(tokenizer.encode(texts[2], add_special_tokens=False))
