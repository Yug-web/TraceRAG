# Architecture

## Implemented foundation

The React app calls GET /api/health through a same-origin relative URL. Vite proxies
/api to 127.0.0.1:8000 during development, avoiding unnecessary CORS configuration.
The browser verifies both the HTTP status and the JSON contract. It handles failure,
timeout, retry, and cancellation on unmount.

FastAPI's create_app factory accepts settings explicitly for tests. Settings are
validated at startup; invalid configuration fails rather than silently falling back.
The health route has no business workflow to extract into a service. A typed response
also produces the OpenAPI schema. No database or provider is contacted.

## Implemented ingestion

POST /api/documents accepts a raw application/pdf body and a display filename query
parameter. The route reads bounded chunks from the request stream before invoking
the synchronous service in a threadpool. Actual bytes are counted, so a missing or
misleading Content-Length cannot bypass the limit. Filenames are validated but never
used as disk paths. Signature checking complements extension and MIME checks; the
parser then validates PDF structure. Strict parsing can reject recoverable PDFs.

The service stores a generated UUID, filename, byte size, SHA-256, processing status,
parser version, and chunk configuration. A first transaction commits processing status.
The parser runs in a separate Python process with a deadline. Successful extraction
publishes pages and chunks and marks the document ready in one transaction. Parser
failures persist a safe error code/message and leave no pages or chunks.

Pages retain their original one-based numbering, including blank pages. Text is
normalized by removing NULs, converting CRLF to LF, and stripping outer whitespace.
Chunks are fixed character windows (default 1000, overlap 200), never crossing a page.
Each stores a stable UUID, document ID, page number, sequential index, and start/end
character offsets into stored page text. End offsets are exclusive. These are character
counts, not token budgets; embedding work will revisit the trade-off.

Foreign keys cascade deletion from document to page to chunk. A row lock during
publication coordinates with deletion: deleting during parsing cannot resurrect the
document. Listing and chunk inspection have bounded pagination. Duplicate uploads
remain distinct documents; the hash records identity but is not a deduplication policy.

There is no background queue: POST waits for processing to complete. Another client
can inspect processing status through the list endpoint while POST is in flight.
An API crash or database outage between transactions can leave processing rows; delete
and re-upload them manually. No automatic recovery claim is made. Database publication
errors roll back partial text/chunks and return 503.

Size/page/text/decoded-stream limits and a killable parser reduce accidental resource
exhaustion, but decompression can allocate memory before limits are checked. The worker
is not an OS security or memory sandbox. Keep this unauthenticated local service off
public networks until resource isolation, concurrency controls, and access control exist.

## Planned boundaries

- API: HTTP validation, response mapping, dependency wiring.
- Services: ingestion, retrieval, evidence selection, generation, citation validation.
- Models/database: document lifecycle and chunks, migrations, vector queries.
- Schemas: public request/response contracts separate from persistence models.
- Evaluation: offline scripts and manually reviewed datasets under evals/.

Stage C adds embeddings to persisted chunks without changing them. Ready continues
to mean extraction/chunking succeeded; embedding coverage is a separate API result.

## Implemented vector baseline

The embedding adapter lazily loads a pinned CPU model. Indexing creates profile-scoped
vectors for existing chunk IDs; publication is atomic and retry-safe. Retrieval embeds
the query using the same profile, then performs exact pgvector cosine-distance search
over fully indexed documents. Source metadata is joined from existing rows, not copied
into a second potentially divergent store. See retrieval.md for the schema, token
window pooling policy, model-switch behavior, and limits. No answer generation exists.

Question flow: retrieve → optionally fuse keyword/vector rankings → optionally
rerank → assess evidence → generate a structured answer → validate citation IDs
against retrieved sources → return answer and passages or insufficient evidence.

Citation existence is not evidence of claim support. Both need evaluation. Retrieved
documents are untrusted data, including any instructions they contain.

## Trade-offs

A modular monolith keeps debugging and deployment understandable. No framework for
agent orchestration or job infrastructure is justified yet. PostgreSQL and pgvector
will keep relational metadata and embeddings together. Page-bounded chunking makes
citations simple but can lose context across page boundaries; benchmark that choice.
Do not create empty modules for future features.

## References

- [SQLAlchemy transaction framing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
  informs the explicit commit/rollback boundaries.
- [pypdf extraction limits](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
  explains memory costs and why scanned documents need OCR.
