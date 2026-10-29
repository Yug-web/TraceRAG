import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.evaluation.dataset import Benchmark, load_benchmark
from app.evaluation.metrics import evaluate_answers, retrieval_metrics
from app.services.embeddings.encoder import LocalEncoder


def rank_chunks(benchmark: Benchmark, encoder: LocalEncoder) -> dict[str, list[str]]:
    chunk_vectors = encoder.encode([chunk.text for chunk in benchmark.chunks])
    query_vectors = encoder.encode([question.query for question in benchmark.questions])
    rankings = {}
    for question, query_vector in zip(benchmark.questions, query_vectors, strict=True):
        scored = [
            (
                sum(left * right for left, right in zip(query_vector, vector, strict=True)),
                chunk.chunk_id,
            )
            for chunk, vector in zip(benchmark.chunks, chunk_vectors, strict=True)
        ]
        if any(not math.isfinite(score) for score, _ in scored):
            raise ValueError("Encoder returned a non-finite similarity")
        rankings[question.question_id] = [
            chunk_id for _, chunk_id in sorted(scored, key=lambda item: (-item[0], item[1]))
        ]
    return rankings


def run(
    dataset_path: Path,
    cutoffs: tuple[int, ...],
    predictions_path: Path | None = None,
) -> dict[str, Any]:
    benchmark = load_benchmark(dataset_path)
    settings = Settings()
    encoder = LocalEncoder(settings)
    rankings = rank_chunks(benchmark, encoder)
    report: dict[str, Any] = {
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "benchmark": {
            "id": benchmark.benchmark_id,
            "version": benchmark.version,
            "license": benchmark.license,
            "documents": len({chunk.document_id for chunk in benchmark.chunks}),
            "chunks": len(benchmark.chunks),
            "questions": len(benchmark.questions),
        },
        "embedding_profile": {
            "id": encoder.profile.id,
            "model": encoder.profile.model_name,
            "revision": encoder.profile.revision,
            "dimensions": encoder.profile.dimensions,
        },
        "retrieval": retrieval_metrics(benchmark, rankings, cutoffs),
        "answer_and_citation": {"status": "not_evaluated", "reason": "No predictions supplied."},
    }
    if predictions_path is not None:
        predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
        report["answer_and_citation"] = {
            "status": "evaluated",
            **evaluate_answers(benchmark, predictions["records"]),
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixed TraceRAG offline benchmark.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--cutoffs", type=int, nargs="+", default=[1, 3, 5])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cutoffs = tuple(sorted(set(args.cutoffs)))
    if not cutoffs or any(cutoff < 1 for cutoff in cutoffs):
        parser.error("cutoffs must be positive integers")
    result = run(args.dataset, cutoffs, args.predictions)
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
