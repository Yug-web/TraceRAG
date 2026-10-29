import json
from pathlib import Path

import pytest

from app.evaluation.dataset import load_benchmark
from app.evaluation.metrics import evaluate_answers, retrieval_metrics

DATASET = Path(__file__).parents[3] / "evals" / "datasets" / "public" / "tracerag_v1.json"


@pytest.fixture(scope="module")
def benchmark():
    return load_benchmark(DATASET)


def test_dataset_is_fixed_and_all_references_resolve(benchmark):
    assert benchmark.benchmark_id == "tracerag-synthetic-v1"
    assert len(benchmark.chunks) == 6
    assert len(benchmark.questions) == 5
    assert sum(question.relevant_chunk_ids == frozenset() for question in benchmark.questions) == 1


def test_retrieval_metrics_include_multi_label_ranks_and_exclusions(benchmark):
    chunk_ids = [chunk.chunk_id for chunk in benchmark.chunks]
    rankings = {question.question_id: list(chunk_ids) for question in benchmark.questions}
    metrics = retrieval_metrics(benchmark, rankings, (1, 3))

    assert metrics["labeled_answerable_questions"] == 4
    assert metrics["unanswerable_questions_excluded"] == 1
    assert metrics["missing_label_questions_skipped"] == 0
    assert metrics["relevant_ranks"]["q-ocean-two-effects"] == [1, 3]
    assert metrics["metrics_at_k"]["1"]["recall"] == pytest.approx(0.375)
    assert metrics["metrics_at_k"]["1"]["precision"] == pytest.approx(0.5)


def test_answer_evaluation_checks_facts_citations_metadata_and_abstention(benchmark):
    gulf = benchmark.chunks[0]
    record = {
        "question_id": "q-gulf-stream",
        "status": "answered",
        "answer": "The current moderates winter temperatures in Western Europe.",
        "citations": ["S1"],
        "sources": [
            {
                "source_id": "S1",
                "id": gulf.chunk_id,
                "document_id": gulf.document_id,
                "filename": gulf.filename,
                "page_number": gulf.page_number,
                "chunk_index": gulf.chunk_index,
                "text": gulf.text,
            }
        ],
    }
    abstention = {
        "question_id": "q-unanswerable-capital",
        "status": "insufficient_evidence",
        "answer": "The evidence is insufficient.",
        "citations": [],
        "sources": [],
    }
    result = evaluate_answers(benchmark, [record, abstention])

    assert result["records_evaluated"] == 2
    assert result["questions_without_records"] == 3
    assert result["status_accuracy"] == 1
    assert result["fact_recall"] == 1
    assert result["supported_fact_recall"] == 1
    assert result["citation_id_accuracy"] == 1
    assert result["citation_metadata_accuracy"] == 1
    assert result["abstention_accuracy"] == 1


def test_answer_evaluation_detects_invalid_source_and_unsupported_fact(benchmark):
    gulf = benchmark.chunks[0]
    result = evaluate_answers(
        benchmark,
        [
            {
                "question_id": "q-gulf-stream",
                "status": "answered",
                "answer": "The Gulf Stream causes milder winters.",
                "citations": ["S9"],
                "sources": [
                    {
                        "source_id": "S1",
                        "id": gulf.chunk_id,
                        "document_id": gulf.document_id,
                        "filename": gulf.filename,
                        "page_number": 99,
                        "chunk_index": gulf.chunk_index,
                        "text": gulf.text,
                    }
                ],
            }
        ],
    )

    assert result["fact_recall"] == 1
    assert result["supported_fact_recall"] == 0
    assert result["citation_id_accuracy"] == 0
    assert result["citation_metadata_accuracy"] == 0


def test_answer_evaluation_rejects_unknown_or_duplicate_questions(benchmark):
    base = {
        "question_id": "unknown",
        "status": "answered",
        "answer": "x",
        "citations": [],
        "sources": [],
    }
    with pytest.raises(ValueError, match="Unknown or duplicate"):
        evaluate_answers(benchmark, [base])

    base["question_id"] = "q-gulf-stream"
    with pytest.raises(ValueError, match="Unknown or duplicate"):
        evaluate_answers(benchmark, [base, base])


def test_dataset_loader_rejects_missing_chunk_reference(tmp_path):
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    data["questions"][0]["relevant_chunk_ids"] = ["30000000-0000-4000-8000-000000000099"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="references missing chunks"):
        load_benchmark(path)
