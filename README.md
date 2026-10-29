# TraceRAG

An evidence-first research assistant in development. The goal is to answer questions
from uploaded documents with inspectable sources and to abstain when evidence is
insufficient. Reliability will be measured, not assumed.

## Current milestone

Stages A–D provide bounded PDF ingestion, source-preserving chunks, retry-safe local
embeddings, pgvector retrieval, grounded Gemini answers, and validated citations.
Stage E adds a responsive research workspace with document/index status, clear upload
and destructive-action feedback, readable answers, expandable passages, provider-aware
errors, and retrieval-only evidence when answer generation is unavailable. Stage F adds
a small synthetic benchmark, deterministic retrieval metrics, labeled answer/citation
scoring, and reliability regression coverage. Hybrid retrieval/reranking remains future
work. See [answer setup](docs/answers.md) and [evaluation methodology](docs/evaluation.md).

## Run locally

Prerequisites: Git, uv 0.12.1, and Node 26.7.0 (the locally verified Node version).
Python 3.13 is managed by uv. Document endpoints require PostgreSQL 18; health does not.
Answer generation requires TRACERAG_GEMINI_API_KEY in backend/.env. Upload and search do not.

From the repository root, in PowerShell:

```powershell
Set-Location backend
uv python install 3.13
uv sync --frozen
# If native PostgreSQL 18 is installed on Windows:
uv run --frozen python scripts/local_postgres.py start
uv run --frozen alembic upgrade head
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal, from the repository root:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Visit http://127.0.0.1:5173. The page should say **Backend connected**.
Stop the backend and select **Check again** to see the failure state; restart it
and check again to recover. A pending request times out after five seconds.
The page checks on mount and on request, not continuously.

API documentation: http://127.0.0.1:8000/docs.

The Windows helper creates a separate local cluster at port 55432, with generated
credentials in ignored local files. It preserves an existing backend/.env; when
bringing your own database, configure TRACERAG_DATABASE_URL there yourself.
See [database setup](docs/development.md#database-setup) for Docker and manual options.

## Ingestion demo

From PowerShell, replace the example path with your own text-based PDF:

```powershell
$document = Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8000/api/documents?filename=research.pdf' `
  -ContentType 'application/pdf' -InFile 'C:\path\research.pdf'
$document
Invoke-RestMethod "http://127.0.0.1:8000/api/documents/$($document.id)/chunks"
Invoke-RestMethod 'http://127.0.0.1:8000/api/documents'
# Remove only the document you just uploaded:
Invoke-RestMethod -Method Delete "http://127.0.0.1:8000/api/documents/$($document.id)"
```

Uploads use a raw PDF body, not multipart/form-data. Defaults: 10 MiB, 100 pages,
2 million extracted characters, and a 20-second parser timeout. Scanned/image-only,
encrypted, empty, and malformed PDFs receive explicit errors. Original files are
not retained; extracted text and its page/chunk metadata are stored in PostgreSQL.

## Index and search

The running native PostgreSQL database needs the pgvector server extension; installing
the Python package alone is insufficient. The Compose image already contains it.
After extension installation, run these commands from backend/:

```powershell
uv sync --frozen
uv run --frozen alembic upgrade head
uv run --frozen python -m app.index_documents --all
```

Indexing uses the persisted chunks, so no re-upload is needed. The default CPU model
is all-MiniLM-L6-v2 with 384 dimensions. First use downloads public model weights;
document/query text stays local. Subsequent indexing skips existing vectors.

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/search' `
  -ContentType 'application/json' `
  -Body '{"query":"What methods does the paper compare?","top_k":5}'
```

See [retrieval architecture and configuration](docs/retrieval.md) for model identity,
long-input handling, indexing coverage, and limitations.

## Offline evaluation

The version-controlled `tracerag-synthetic-v1` benchmark contains two synthetic
documents, six fixed chunks, four answerable questions, and one unanswerable question.
It does not use uploaded documents or call Gemini. From `backend/`:

```powershell
$env:TRACERAG_EMBEDDING_LOCAL_FILES_ONLY='true' # after the model is cached
uv run --frozen python -m app.evaluation.runner `
  --dataset ../evals/datasets/public/tracerag_v1.json `
  --cutoffs 1 3 5
```

Optionally pass `--predictions path/to/predictions.json` to score captured answer
records against expected facts and citation metadata. Keep private or provider-generated
outputs under ignored `evals/results/`. The checked-in [evaluation report](docs/evaluation-report.md)
distinguishes executed retrieval measurements from unverified live answer quality.

## Checks

```powershell
# In backend/
# Runs all tests using the helper's separate tracerag_test database:
uv run --frozen python scripts/local_postgres.py test
# Or set TRACERAG_TEST_DATABASE_URL to your own disposable database ending in _test:
uv run --frozen pytest
# Include cached/downloaded real-model checks explicitly:
# $env:TRACERAG_REAL_MODEL_TESTS='1'
uv run --frozen ruff check .
uv run --frozen ruff format --check .

# In frontend/
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

## Architecture and roadmap

The planned architecture is a modular monolith: React → FastAPI services →
PostgreSQL/pgvector, with isolated PDF, embedding, and LLM integrations.
Current ingestion flow: PDF request → bounded reader → parser subprocess →
page-bounded chunks → PostgreSQL transaction. React supports document management and grounded questions.

Future milestones: measured hybrid retrieval/reranking;
deployment hardening.

- [Architecture and decisions](docs/architecture.md)
- [Development and version policy](docs/development.md)
- [API contract](docs/api.md)
- [Embedding and retrieval design](docs/retrieval.md)
- [Evaluation methodology](docs/evaluation.md)
- [Latest evaluation report](docs/evaluation-report.md)
- [Development log](docs/development-log.md)

## Limits

This is a local development project, not a deployed research product. Health
means the API process responds; it says nothing about database or model readiness.
There is no authentication. Vite's proxy is development-only; the production build
will need a same-origin reverse proxy when deployment is implemented. Do not put
provider secrets in frontend variables. Never commit private documents or datasets.
The parser timeout is not a hard memory sandbox. Complex PDFs can consume substantial
memory during decompression. No OCR, durable job queue, automatic crash recovery,
or multi-user isolation is provided yet. See the architecture notes for details.
