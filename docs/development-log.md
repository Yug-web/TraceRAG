# Development log

## 2026-10-28 — Milestone 1 foundation

- Inspected an empty workspace; initialized a local Git repository on main after approval.
- Added a typed FastAPI liveness endpoint and validated environment configuration.
- Added a React status page with timeout, cancellation, failure, and retry behavior.
- Added backend and frontend tests, lint/type/build commands, and a CI workflow.
- Recorded architecture boundaries, setup, API contract, evaluation plan, and limitations.
- Resolved a TypeScript 7 / typescript-eslint peer dependency conflict by choosing 6.0.x.
- Used the downloaded Python executable explicitly after uv's registration link failed.

Verification completed locally:

- Backend: 7 pytest tests passed; Ruff lint and formatting checks passed.
- Frontend: 8 tests passed; ESLint, strict TypeScript checking, and production build passed.
- Browser smoke test: the rendered page displayed Backend connected through Vite's proxy.
- Git whitespace check passed; environment, dependency, and build files are ignored.
- Backend tests emit one upstream Starlette warning that HTTPX support in TestClient
  is deprecated in favor of httpx2. Tests pass; migrate the test transport in a future
  dependency maintenance change. No warnings were suppressed.
- Sandboxed process/socket restrictions stalled initial tests and development servers;
  the backend tests and both live servers were verified outside the sandbox. Stalled
  processes were stopped.

GitHub Actions has not run remotely. No commit or push has been made.

## 2026-10-28 — Milestone 2 PDF ingestion

- Added PostgreSQL document/page/chunk models and an explicit Alembic migration.
- Added raw PDF upload with streamed size enforcement, filename/MIME/signature
  validation, strict parsing, parser timeout, and page/text/decoded-stream limits.
- Preserved blank page numbers and stored source text offsets with deterministic chunks.
- Added persistent processing/ready/failed metadata, list/detail/chunk APIs, and
  cascade deletion. Original PDFs are not retained.
- Added a native Windows PostgreSQL helper and a database-only Compose option.
  Created a separate project-owned local cluster on port 55432 with generated credentials
  in ignored files; existing PostgreSQL services were not modified.
- Added PostgreSQL to CI and generated synthetic PDF fixtures for tests.
- Fixed a service method name that shadowed the built-in list type during the first run.
- Verified 48 backend tests with no skips against real PostgreSQL, including migration
  round-trip/model agreement, transaction rollback, safe errors, and cross-app persistence.
- Ruff lint and formatting passed; Git whitespace checks passed.
- Live HTTP demo: upload returned 201/ready, three pages preserved with chunks on pages
  1 and 3, deletion returned 204, and subsequent lookup returned 404. The synthetic
  document was removed afterward.
- The existing upstream HTTPX/Starlette test-client deprecation warning remains.
  Docker Compose and hosted CI were not run; the frontend was not changed in this milestone.

Milestones 1 and 2 remain uncommitted pending user review. No retrieval or embeddings
have been implemented. Memory isolation and crash recovery remain future work.

## Stage C — local embeddings and exact vector retrieval

- Backed up the application database and recorded original chunk IDs/text hashes in
  ignored local files before migration.
- Installed Microsoft C++ Build Tools, compiled official pgvector 0.8.7 for native
  PostgreSQL 18, and installed runtime files with Windows administrator elevation.
  Verified extension version 0.8.7 and Alembic revision 0002.
- Added lazily loaded, pinned MiniLM CPU embeddings with 384 dimensions and versioned
  token-window pooling for inputs exceeding the model's token limit.
- Added embedding profiles and chunk vectors with dimension checks, source foreign
  keys, atomic publication, and duplicate protection under concurrent retries.
- Added explicit index/index-status endpoints, an index-existing-documents CLI, and
  POST /api/search with exact cosine distance and preserved source metadata.
- Fixed two issues caught during verification: removed tokenizer prepare_for_model
  was replaced with supported overflow tokenization; unreliable Psycopg rowcount was
  replaced with INSERT RETURNING to count actually inserted vectors.
- Reconciled the lockfile after an interrupted install and restarted the project-owned
  database after its process stopped. Migration connections now have a timeout.
- Redacted test database URL representations and rotated the generated local database
  credential after a failed test displayed it. Private configuration remains ignored.
- Final verification: 77 tests passed, including the opt-in cached real-model test and
  actual PostgreSQL/pgvector tests; no tests skipped. Ruff lint/format and git diff
  whitespace checks passed. Hosted CI and Docker Compose were not run.
- Indexed the existing real document: 15 embeddings created. Repeated indexing:
  0 created, 15 skipped. Its 10 pages and 15 original chunk IDs, page references,
  indices, and text hashes remained unchanged.
- Live HTTP search returned 200 with 3 ranked results and matching source metadata.
  Live index retry skipped all 15 vectors; a blank query returned 422.

This is the Stage C vector baseline. No semantic retrieval-quality benchmark, hybrid
ranking, reranking, or LLM generation has been implemented. All work remains
uncommitted and unpushed for user review.
