import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class BenchmarkChunk:
    chunk_id: str
    document_id: str
    filename: str
    page_number: int
    chunk_index: int
    text: str


@dataclass(frozen=True)
class ExpectedFact:
    fact_id: str
    accepted_phrases: tuple[str, ...]
    supporting_chunk_ids: frozenset[str]


@dataclass(frozen=True)
class BenchmarkQuestion:
    question_id: str
    query: str
    relevant_chunk_ids: frozenset[str] | None
    expected_status: Literal["answered", "insufficient_evidence"]
    facts: tuple[ExpectedFact, ...]


@dataclass(frozen=True)
class Benchmark:
    benchmark_id: str
    version: int
    license: str
    description: str
    chunks: tuple[BenchmarkChunk, ...]
    questions: tuple[BenchmarkQuestion, ...]


def load_benchmark(path: Path) -> Benchmark:
    raw = json.loads(path.read_text(encoding="utf-8"))
    chunks: list[BenchmarkChunk] = []
    chunk_ids: set[str] = set()
    document_ids: set[str] = set()
    for document in raw["documents"]:
        document_id = str(UUID(document["document_id"]))
        if document_id in document_ids:
            raise ValueError(f"Duplicate document_id: {document_id}")
        document_ids.add(document_id)
        for item in document["chunks"]:
            chunk_id = str(UUID(item["chunk_id"]))
            if chunk_id in chunk_ids:
                raise ValueError(f"Duplicate chunk_id: {chunk_id}")
            chunk_ids.add(chunk_id)
            chunks.append(
                BenchmarkChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    filename=document["filename"],
                    page_number=item["page_number"],
                    chunk_index=item["chunk_index"],
                    text=item["text"],
                )
            )

    questions: list[BenchmarkQuestion] = []
    question_ids: set[str] = set()
    for item in raw["questions"]:
        question_id = item["question_id"]
        if question_id in question_ids:
            raise ValueError(f"Duplicate question_id: {question_id}")
        question_ids.add(question_id)
        labels = item.get("relevant_chunk_ids")
        relevant = None if labels is None else frozenset(labels)
        referenced = set() if relevant is None else set(relevant)
        facts = tuple(
            ExpectedFact(
                fact_id=fact["fact_id"],
                accepted_phrases=tuple(fact["accepted_phrases"]),
                supporting_chunk_ids=frozenset(fact["supporting_chunk_ids"]),
            )
            for fact in item["facts"]
        )
        referenced.update(chunk for fact in facts for chunk in fact.supporting_chunk_ids)
        missing = referenced - chunk_ids
        if missing:
            raise ValueError(f"Question {question_id} references missing chunks: {sorted(missing)}")
        expected_status = item["expected_status"]
        if expected_status == "insufficient_evidence" and (relevant or facts):
            raise ValueError(f"Unanswerable question {question_id} must have no labels or facts")
        questions.append(
            BenchmarkQuestion(
                question_id=question_id,
                query=item["query"],
                relevant_chunk_ids=relevant,
                expected_status=expected_status,
                facts=facts,
            )
        )

    return Benchmark(
        benchmark_id=raw["benchmark_id"],
        version=raw["version"],
        license=raw["license"],
        description=raw["description"],
        chunks=tuple(chunks),
        questions=tuple(questions),
    )
