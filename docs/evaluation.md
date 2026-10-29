# Evaluation methodology

TraceRAG keeps retrieval measurement, deterministic answer/citation checks, API
reliability tests, and optional live-provider evaluation separate. A passing mocked
test or labeled offline record is not evidence that Gemini produced a good live answer.

## Fixed benchmark

`evals/datasets/public/tracerag_v1.json` is a CC0 synthetic benchmark written for this
project. Stable document and chunk UUIDs make labels reproducible. Its two documents
contain six passages about ocean climate effects and sunlight conversion. Five questions
cover one-passage facts, a two-passage/two-page answer, a photosynthesis distractor for
a photovoltaic question, and an intentionally unanswerable general-knowledge question.

Each answerable question declares relevant chunk IDs and expected facts. A fact has
accepted phrases and one or more supporting chunk IDs. Document ID, filename, page,
chunk index, and passage text come from the fixed chunk record. The loader rejects
duplicate IDs and references to missing chunks.

An empty `relevant_chunk_ids` list is an explicit unanswerable label. A missing field
means relevance was not labeled; such questions are counted and skipped rather than
silently scored as misses. The current dataset has no missing labels.

## Retrieval metrics

The offline runner embeds the fixed passages and questions with the application's
configured `LocalEncoder`, then ranks every passage by cosine similarity with stable
chunk-ID tie breaking. It does not exercise PostgreSQL query planning, ingestion, or
chunking; those are covered by integration tests.

For answerable questions only:

- Recall@k is relevant chunks in the first k results divided by all labeled relevant chunks.
- Precision@k is relevant chunks in the first k results divided by k.
- MRR@k averages the reciprocal rank of the first relevant chunk, or zero when none is in k.
- Relevant ranks list the exact one-based positions of every labeled chunk.

Unanswerable questions have no relevant target and are reported separately. They are
not included in Recall, Precision, or MRR.

## Answer and citation checks

The optional predictions input is JSON with a top-level `records` array. Each record
uses the `/api/ask` response fields plus `question_id`. The evaluator measures status,
expected-phrase coverage, whether each detected expected fact cites a labeled supporting
chunk, whether citation source IDs exist, exact source metadata, and correct abstention.

These checks are deliberately narrow. Phrase matching can miss a valid paraphrase or
accept text in a misleading context. Labeled citation support shows that an expected
fact points to an expected passage; it does not prove every generated claim is entailed,
factually correct, or complete. Human review remains necessary.

## Commands

From `backend/`, after the configured embedding model is available:

```powershell
$env:TRACERAG_EMBEDDING_LOCAL_FILES_ONLY='true'
uv run --frozen python -m app.evaluation.runner `
  --dataset ../evals/datasets/public/tracerag_v1.json `
  --cutoffs 1 3 5

# Optional; provider-generated output should remain in ignored evals/results/.
uv run --frozen python -m app.evaluation.runner `
  --dataset ../evals/datasets/public/tracerag_v1.json `
  --predictions ../evals/results/predictions.json
```

The runner prints JSON or writes it with `--output`. Do not commit private passages,
credentials, raw provider payloads, or generated result files.

## Reliability boundary

Backend tests cover empty and unindexed corpora, malformed requests, missing documents,
retry-safe indexing, citation validation, malformed model output, provider timeout,
HTTP 503, rate limiting, authentication failure, retry exhaustion, deadline exhaustion,
and safe API error envelopes. Provider calls are mocked. The optional real embedding
smoke test is disabled unless explicitly enabled; no live Gemini test is part of the
default suite.
