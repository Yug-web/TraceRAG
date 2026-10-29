# Development

## Setup and configuration

Use the commands in the root README. Run backend commands from backend/: .env is
resolved relative to the working directory. OS environment variables override .env.
Copy .env.example only when .env does not already contain your settings.

| Setting | Default | Validation |
| --- | --- | --- |
| TRACERAG_APP_NAME | TraceRAG | Nonempty after whitespace trimming |
| TRACERAG_ENVIRONMENT | development | development, test, or production |

The environment label does not enable authentication or hardening automatically.
No frontend environment variables are required. Keep API credentials server-side.

## Version policy

Python is constrained to 3.13.x. Backend direct dependencies have major-version
upper bounds in pyproject.toml; uv.lock records the exact resolved dependency graph.
Frontend direct dependencies are constrained in package.json; package-lock.json
records exact versions. Use uv sync --frozen and npm ci to reproduce installations.
Update dependencies deliberately and rerun checks before reviewing a lockfile diff.

Selected versions resolved and checked for milestone 1:

| Component | Version |
| --- | --- |
| Python | 3.13.14 |
| FastAPI / Uvicorn | 0.162.0 / 0.54.0 |
| Pydantic / pydantic-settings | 2.14.1 / 2.16.1 |
| pytest / Ruff | 9.1.1 / 0.17.3 |
| React / Vite | 19.3.1 / 8.3.5 |
| TypeScript | 6.0.x (exact patch in package-lock.json) |
| Vitest / ESLint | 5.0.5 / 10.13.0 |

Starlette emits a deprecation warning for HTTPX in TestClient. The latest local Stage G
backend run passed 111 tests with one optional real-model test skipped; a future
maintenance change should migrate to the recommended transport.

The Vite scaffold initially selected TypeScript 7, which conflicted with
typescript-eslint's declared <6.1 peer range. TypeScript is constrained to 6.0.x.
ESLint replaces the scaffold's Oxlint to match the approved milestone tooling.

## Windows setup troubleshooting

The system python alias failed during initial inspection. Use uv rather than relying
on that alias. On this machine uv downloaded Python 3.13.14, but registering its minor
version link failed. Installation succeeded by giving uv sync the downloaded python.exe
explicitly with --python. The resulting backend/.venv is the local project interpreter.
This machine-specific path must not be copied into manifests or CI.

If uv cannot write its global cache, resolve the permission issue or use an accessible
cache directory with --cache-dir. Registry downloads require network access. OneDrive
can complicate file access; a regular local checkout is an option if problems persist.

## Review workflow

Keep each milestone small. Run checks, inspect git diff (including new files), review
secrets and generated outputs, and propose a commit message. Local commits require
user approval; do not push automatically. Do not commit .env, virtual environments,
node_modules, uploads, private datasets, or build outputs.

GitHub Actions runs backend tests/lint/format checks and frontend tests/lint/type
checking/build on push and pull request. The initial published `main` run completed
successfully for both jobs on commit `0e410a1`; later workflow status must be checked
on GitHub rather than inferred from the file.

## Database setup

For native PostgreSQL 18 on Windows, from backend/:

```powershell
uv run --frozen python scripts/local_postgres.py start
uv run --frozen alembic upgrade head
```

The helper uses C:\Program Files\PostgreSQL\18\bin by default; override --bin-dir
if needed. It creates a project-owned cluster under ignored .local-data/postgres,
binds to 127.0.0.1:55432, and uses SCRAM password authentication. It does not modify
the existing Windows PostgreSQL service. Credentials are generated into ignored
.local-data/postgres-password.txt and backend/.env (only if .env does not exist).
Keep these files private. The local app uses the cluster administrator role for
convenience; deployment requires a restricted application role. Avoid cloud-syncing
live database directories; use a regular local checkout for sustained development.

Stop the project cluster with:

```powershell
uv run --frozen python scripts/local_postgres.py stop
```

Alternatively, install Docker and set POSTGRES_PASSWORD in the shell, then run
`docker compose up -d db` from the repository root. Compose starts only PostgreSQL,
not FastAPI or React. The service uses the pgvector PostgreSQL 18 image, binds container
port 5432 to host `127.0.0.1:55432`, checks readiness with `pg_isready`, and persists
data in the named `postgres_data` volume. Do not start it alongside the native helper
on the same port. Put the matching `postgresql+psycopg://` URL in `backend/.env`, then
run `uv run --frozen alembic upgrade head`; migration 0002 creates the vector extension
and embedding tables. Stop the service with `docker compose down`. The named volume is
retained unless `docker compose down --volumes` is deliberately used.

The pg18 tag tracks patch updates; pin a reviewed digest for deployment. Docker is not
installed on the current verification machine, so this Compose workflow has been
reviewed but not executed locally.

For an existing database, create an empty database and configure TRACERAG_DATABASE_URL
with the postgresql+psycopg driver. Alembic is the only schema creation mechanism;
the app does not auto-create tables. Run alembic upgrade head before serving requests.

## Ingestion configuration

| Variable suffix (prefix TRACERAG_) | Default |
| --- | --- |
| DATABASE_URL | unset; document endpoints return 503 |
| MAX_UPLOAD_BYTES | 10485760 (10 MiB) |
| MAX_PDF_PAGES | 100 |
| MAX_TEXT_CHARS | 2000000 |
| MAX_PAGE_STREAM_BYTES | 5242880 |
| PARSE_TIMEOUT_SECONDS | 20 |
| CHUNK_SIZE / CHUNK_OVERLAP | 1000 / 200 characters |

Overlap must be smaller than chunk size; nonpositive limits fail settings validation.
Gemini credentials are not required for upload, indexing, or search, but generated
answers require a valid `TRACERAG_GEMINI_API_KEY`. Use `--no-access-log` with Uvicorn
if filenames in request URLs should not appear in access logs. Application errors log
exception types without raw document text, SQL parameters, or database credentials.

`GET /api/health` checks FastAPI process liveness only. It does not connect to the
database, load the embedding model, or contact Gemini. A healthy response therefore
does not establish application readiness.

## Database tests

The native helper's test action supplies the generated credentials without printing
them: uv run --frozen python scripts/local_postgres.py test. Other environments set
TRACERAG_TEST_DATABASE_URL explicitly. It must point to a disposable database whose
name ends in _test. Tests truncate documents and exercise migration downgrade/upgrade;
never point this at a database containing valuable data. Without that variable, database
tests are skipped and the output must not be reported as a full integration pass.
CI supplies a PostgreSQL service and the variable so those tests execute.

PDF fixtures are generated from synthetic strings in tests/pdf_factory.py. No private
or downloaded documents are used. Integration tests verify actual PostgreSQL behavior,
foreign-key deletion, the worker process, and migration/model agreement.

Milestone 2 resolved SQLAlchemy 2.0.55, Alembic 1.20.1, Psycopg 3.3.6, and pypdf 6.21.3.
The exact dependency graph is in uv.lock.

## Stage C native extension and model setup

The native Windows PostgreSQL installation initially had no pgvector extension.
Stage C built pgvector 0.8.7 from the official release source using Microsoft Visual
Studio 2022 C++ Build Tools, then installed its runtime files under PostgreSQL 18
with administrator elevation. Migration 0002 enables it in each target database.
Installing the Python pgvector package is not a replacement for this server setup.
The Compose/CI image includes the server files and can apply the same migration.

An ignored pre-migration backup is at .local-data/before-stage-c.dump. It contains
private document data: keep it private. A separate ignored chunk ID/hash snapshot is
used to check that indexing does not mutate sources. Do not restore over current data
without deliberately choosing a recovery operation.

Stage C resolved pgvector (Python) 0.5.1, sentence-transformers 5.7.0, Transformers
5.21.0, and PyTorch 2.14.1. The adapter uses the supported tokenizer overflow API,
not the removed prepare_for_model method. Frozen installs reproduce the lockfile.

Run the complete local checks, including the real cached model, from backend/:

```powershell
$env:TRACERAG_REAL_MODEL_TESTS='1'
$env:TRACERAG_EMBEDDING_LOCAL_FILES_ONLY='true'
uv run --frozen python scripts/local_postgres.py test
```

For the first model download, leave LOCAL_FILES_ONLY false. Public model files are
cached by Hugging Face; weights are not committed. Windows may warn that its cache
cannot use symlinks; extra disk use does not invalidate the model test. Test database
URLs have a redacted representation to prevent credentials appearing in failure reports.
