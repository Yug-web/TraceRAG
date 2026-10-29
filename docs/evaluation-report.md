# Stage F evaluation report

Run date: 2026-10-29 (UTC)

## Dataset and assumptions

- Benchmark: `tracerag-synthetic-v1`, version 1, CC0-1.0
- Corpus: 2 synthetic documents, 6 fixed passages
- Questions: 5 total; 4 labeled answerable and 1 explicitly unanswerable
- Missing relevance labels: 0
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Revision: `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
- Dimensions: 384
- Profile ID: `22c885f361a3a47ebd46079c1891c613511802de2d9e085fce7973f2d0ddeeea`

The offline run used locally cached model files and exact cosine ranking over all six
fixed chunks. It did not use PostgreSQL or the user's uploaded PDF.

## Executed retrieval results

| k | Recall@k | Precision@k | MRR@k |
|---:|---:|---:|---:|
| 1 | 0.875 | 1.000 | 1.000 |
| 3 | 1.000 | 0.417 | 1.000 |
| 5 | 1.000 | 0.250 | 1.000 |

Relevant chunk ranks:

- Gulf Stream: 1
- Thermohaline driver: 1
- Two ocean effects: 1 and 3
- Photovoltaic question with photosynthesis distractor: 1

The sole Recall@1 miss is the second relevant passage in the intentionally multi-passage
question. Precision naturally falls as k grows because this tiny corpus has only one or
two labeled passages per question. These scores are descriptive for this benchmark, not
a claim of general RAG quality.

## Answer and citation evaluation

Status: **not executed**. No saved live Gemini predictions were supplied, and this stage
made no Gemini requests. Unit tests execute the scoring logic with hand-authored records,
but those tests only verify evaluator behavior and are not model-quality measurements.

Live answer correctness, paraphrase quality, claim-level entailment, and citation
completeness therefore remain unverified.

## Reliability results

The full backend suite ran against the isolated `tracerag_test` PostgreSQL/pgvector
database: **111 passed, 1 skipped** in 76.50 seconds. The skip was the explicitly opt-in
real embedding model smoke test. The run included stable API responses for mocked provider
timeouts, HTTP 503 temporary unavailability, rate limits, and authentication failures,
as well as existing retry/deadline, malformed output, citation, retrieval, indexing,
ingestion, and missing-document cases.

Focused evaluator tests: **6 passed**. Backend Ruff lint and format checks both passed,
and `git diff --check` found no whitespace errors.

## Limitations and next steps

- Six short passages are too small to estimate production retrieval quality or confidence.
- The runner evaluates embedding/ranking behavior, not PostgreSQL execution or PDF chunking.
- Relevance labels were authored with the synthetic text and have not had independent review.
- Exact phrase matching is not a semantic correctness or entailment judge.
- Citation validation proves references exist and match labels; it does not prove correctness.
- Live provider answer quality remains unverified because no live evaluation was run.
