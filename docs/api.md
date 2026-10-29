# API specification

The executable machine-readable specification is GET /openapi.json; interactive
documentation is GET /docs. These are generated from FastAPI routes and schemas.

## GET /api/health

No authentication, parameters, body, or external dependencies.

Successful response: HTTP 200, application/json:

```json
{"status":"ok"}
```

This reports process liveness only. It does not check storage, embeddings, or an LLM.
The frontend treats non-2xx responses, invalid JSON, unexpected status values,
network failures, and a five-second timeout as unavailable. Errors are not displayed
verbatim in the UI. Unsupported routes use FastAPI's normal 404 response.

## Documents

| Method and path | Behavior |
| --- | --- |
| POST /api/documents?filename=name.pdf | Raw application/pdf body; returns 201 document metadata after processing |
| GET /api/documents | Metadata list, ordered newest first; limit=20, offset=0 |
| GET /api/documents/{uuid} | Metadata and processing/ready/failed status |
| GET /api/documents/{uuid}/chunks | Ordered source chunks; limit=20, offset=0 |
| DELETE /api/documents/{uuid} | 204; cascades deletion of pages and chunks |

Pagination limits range from 1 to 100, offsets must be nonnegative. Invalid UUIDs and
query parameters return FastAPI's standard 422 validation response. Missing documents
return 404. The upload is synchronous; it does not return a job or a 202 response.
Upload size is enforced from bytes actually received, independently of Content-Length.
Request compression and multipart/form-data are not accepted.

Metadata includes id, filename, sha256, size_bytes, status, page_count, chunk_count,
chunk_size, chunk_overlap, parser_version, error_code, error_message, and created_at.
Chunk data includes id, document_id, page_number, chunk_index, start_char, end_char,
and text. Chunk indices and offsets are zero-based; page numbers are one-based.

Application errors use:

```json
{"detail":{"code":"no_text","message":"No readable text found. Scanned PDFs require OCR.","document_id":"UUID of failed document"}}
```

Validation before processing creates no document; document_id is null. Failures after
the processing record is created return its ID so it can be inspected or deleted.
Do not infer search readiness from ready: it currently means extraction/chunking only.

| Status | Example codes |
| --- | --- |
| 413 | file_too_large |
| 415 | unsupported_type, unsupported_encoding |
| 422 | invalid_filename, empty_file, invalid_pdf, encrypted_pdf, no_text, too_many_pages, too_much_text, complex_pdf, parse_timeout, parser_failed |
| 404 | not_found |
| 500 | processing_failed (unexpected non-database processing error) |
| 503 | database_unavailable |

Original PDF bytes are discarded after extraction; there is no PDF download endpoint.
POST /api/ask provides grounded answers. See [request/response contract, errors and configuration](answers.md).

## Indexing and search

POST /api/documents/{uuid}/index generates missing embeddings from persisted chunks.
It returns HTTP 200 with document_id, profile_id, total_chunks, indexed_chunks,
complete, created_embeddings, and skipped_embeddings. Repeating it does not create
duplicate chunks or vectors. It does not modify the ingestion status.

GET /api/documents/{uuid}/index-status returns the same coverage fields without
created/skipped counts. Coverage always refers to the currently configured profile.

POST /api/search accepts JSON:

```json
{"query":"What methods does the paper compare?","top_k":5}
```

Query whitespace is stripped; query length must be 1–2000 characters. top_k is an
integer from 1–20, default 5. Unknown fields are rejected. HTTP 200 responses contain
profile_id, model_name, dimensions, ready_documents, indexed_documents,
unindexed_documents, and results. Each result contains all chunk inspection fields
plus filename and cosine_distance (lower is closer). Results have deterministic ID
tie-breaking. Scores are not calibrated confidence or evidence-sufficiency measures.

An empty ready corpus returns an empty results list. A ready corpus without any fully
indexed documents for the active profile returns 409 index_required. Partially indexed
documents are excluded and counted in unindexed_documents. A model load/inference
failure or invalid vector output returns 503 embedding_unavailable. Indexing a document
that is not ready returns 409 document_not_ready. A source change during indexing
returns 409 document_changed; deletion returns 404. Existing validation and database
error conventions apply. These endpoints use exact vector retrieval only.
