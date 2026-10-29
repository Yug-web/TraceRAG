import re
from dataclasses import dataclass
from statistics import fmean
from typing import Any

from app.evaluation.dataset import Benchmark


@dataclass(frozen=True)
class RetrievalQuestionResult:
    question_id: str
    relevant_ranks: tuple[int, ...]


def retrieval_metrics(
    benchmark: Benchmark,
    rankings: dict[str, list[str]],
    cutoffs: tuple[int, ...],
) -> dict[str, Any]:
    labeled = [question for question in benchmark.questions if question.relevant_chunk_ids]
    unlabeled = [
        question for question in benchmark.questions if question.relevant_chunk_ids is None
    ]
    unanswerable = [
        question for question in benchmark.questions if question.relevant_chunk_ids == frozenset()
    ]
    per_question = []
    for question in labeled:
        ranked = rankings[question.question_id]
        ranks = tuple(
            index
            for index, chunk_id in enumerate(ranked, start=1)
            if chunk_id in question.relevant_chunk_ids
        )
        per_question.append(RetrievalQuestionResult(question.question_id, ranks))

    by_k: dict[str, dict[str, float]] = {}
    for cutoff in cutoffs:
        recalls = []
        precisions = []
        reciprocal_ranks = []
        for question, result in zip(labeled, per_question, strict=True):
            hits = sum(rank <= cutoff for rank in result.relevant_ranks)
            recalls.append(hits / len(question.relevant_chunk_ids))
            precisions.append(hits / cutoff)
            first = min(result.relevant_ranks, default=0)
            reciprocal_ranks.append(1 / first if first and first <= cutoff else 0.0)
        by_k[str(cutoff)] = {
            "recall": fmean(recalls) if recalls else 0.0,
            "precision": fmean(precisions) if precisions else 0.0,
            "mrr": fmean(reciprocal_ranks) if reciprocal_ranks else 0.0,
        }
    return {
        "labeled_answerable_questions": len(labeled),
        "unanswerable_questions_excluded": len(unanswerable),
        "missing_label_questions_skipped": len(unlabeled),
        "metrics_at_k": by_k,
        "relevant_ranks": {
            result.question_id: list(result.relevant_ranks) for result in per_question
        },
    }


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _fact_present(answer: str, phrases: tuple[str, ...]) -> bool:
    normalized = _normalize(answer)
    return any(_normalize(phrase) in normalized for phrase in phrases)


def evaluate_answers(benchmark: Benchmark, records: list[dict[str, Any]]) -> dict[str, Any]:
    questions = {question.question_id: question for question in benchmark.questions}
    chunks = {chunk.chunk_id: chunk for chunk in benchmark.chunks}
    seen: set[str] = set()
    results = []
    for record in records:
        question_id = record.get("question_id")
        if question_id not in questions or question_id in seen:
            raise ValueError(f"Unknown or duplicate question_id: {question_id}")
        seen.add(question_id)
        question = questions[question_id]
        sources = record.get("sources", [])
        source_by_id = {source.get("source_id"): source for source in sources}
        citation_ids = record.get("citations", [])
        cited_sources = [source_by_id.get(identifier) for identifier in citation_ids]
        citation_ids_valid = all(source is not None for source in cited_sources)
        metadata_valid = citation_ids_valid and all(
            _source_metadata_matches(source, chunks)
            for source in cited_sources
            if source is not None
        )
        cited_chunks = {
            source["id"] for source in cited_sources if source is not None and source.get("id")
        }
        present_facts = [
            fact
            for fact in question.facts
            if _fact_present(record.get("answer", ""), fact.accepted_phrases)
        ]
        supported_facts = [
            fact for fact in present_facts if cited_chunks.intersection(fact.supporting_chunk_ids)
        ]
        status_correct = record.get("status") == question.expected_status
        abstention_correct = question.expected_status != "insufficient_evidence" or (
            status_correct and not citation_ids
        )
        results.append(
            {
                "question_id": question_id,
                "status_correct": status_correct,
                "fact_recall": len(present_facts) / len(question.facts) if question.facts else None,
                "supported_fact_recall": (
                    len(supported_facts) / len(question.facts) if question.facts else None
                ),
                "citation_ids_valid": citation_ids_valid,
                "citation_metadata_valid": metadata_valid,
                "abstention_correct": abstention_correct,
            }
        )
    answerable = [result for result in results if result["fact_recall"] is not None]
    return {
        "records_evaluated": len(results),
        "questions_without_records": len(benchmark.questions) - len(results),
        "status_accuracy": _mean_bool(results, "status_correct"),
        "fact_recall": _mean_number(answerable, "fact_recall"),
        "supported_fact_recall": _mean_number(answerable, "supported_fact_recall"),
        "citation_id_accuracy": _mean_bool(results, "citation_ids_valid"),
        "citation_metadata_accuracy": _mean_bool(results, "citation_metadata_valid"),
        "abstention_accuracy": _mean_bool(
            [result for result in results if result["fact_recall"] is None],
            "abstention_correct",
        ),
        "per_question": results,
    }


def _source_metadata_matches(source: dict[str, Any], chunks: dict[str, Any]) -> bool:
    chunk = chunks.get(source.get("id"))
    return bool(
        chunk
        and source.get("document_id") == chunk.document_id
        and source.get("filename") == chunk.filename
        and source.get("page_number") == chunk.page_number
        and source.get("chunk_index") == chunk.chunk_index
        and source.get("text") == chunk.text
    )


def _mean_bool(results: list[dict[str, Any]], key: str) -> float | None:
    return fmean(float(result[key]) for result in results) if results else None


def _mean_number(results: list[dict[str, Any]], key: str) -> float | None:
    return fmean(result[key] for result in results) if results else None
