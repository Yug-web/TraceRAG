# Stage D: grounded answers

Set TRACERAG_GEMINI_API_KEY privately in backend/.env and restart the backend.
Never put secrets in frontend variables or logs. TRACERAG_LLM_MODEL defaults to
 gemini-3.8-flash; select a structured-output model available to your account.
TRACERAG_LLM_TIMEOUT_SECONDS defaults to 30 (1–120), LLM_MAX_OUTPUT_TOKENS to
2048 (128–8192), and QA_CONTEXT_CHARS to 12000 (1000–40000). All settings use
TRACERAG_ prefixes. Only the Gemini provider is implemented.

POST /api/ask accepts {"question":"What does the paper conclude?","top_k":5}.
Questions are trimmed and limited to 1–2000 characters; top_k is a strict integer
1–20. Unknown fields are rejected. AnswerService reuses RetrievalService and sends
selected passages and the question to Gemini. Evidence has a character budget;
the last passage can be truncated, with end_char adjusted to match.

Responses contain status (answered or insufficient_evidence), answer, citations
(source-ID strings), sources, model, retrieval_profile_id, indexed_documents and
unindexed_documents. Each source has source_id, chunk id, document_id, filename,
page_number (one-based), chunk_index (zero-based), start_char, exclusive end_char,
text and cosine_distance. Metadata comes from retrieval, never from the LLM.
Sources include selected but uncited passages as well as cited passages.

An empty corpus returns insufficient_evidence without calling Gemini. An unindexed
ready corpus returns 409 index_required. Unknown citation IDs, answers without
citations, malformed outputs and contradictory statuses are rejected. Duplicate
valid IDs are collapsed. Abstentions use a fixed safe message.

Errors use the existing detail/code/message/document_id envelope: 429
provider_rate_limited; 504 provider_timeout; 503 llm_not_configured,
provider_auth_failed, provider_temporarily_unavailable or provider_unavailable; 502 invalid_model_output or
invalid_citations. SDK errors are not exposed. The SDK retry loop is disabled and
the application makes at most two attempts for explicitly transient transport
failures and HTTP 408, 429, 500, 502, 503, or 504 responses. A short exponential
delay with jitter separates attempts. Both attempts and the delay share the overall
generation deadline.

Citation validation establishes source membership, NOT factual correctness or
claim support. Prompt instructions cannot guarantee resistance to prompt injection.
Similarity is not confidence. Extraction errors, retrieval misses and truncation
can omit evidence. No answer-quality or retrieval-quality evaluation is claimed.

## Tests and browser verification

Use the README Checks commands for backend pytest/Ruff and frontend lint,
typecheck, Vitest and production build. Database tests use a disposable _test
database, synthetic PDFs, deterministic embeddings and mocked Gemini responses.
TRACERAG_REAL_MODEL_TESTS=1 enables the optional real embedding test.
No automated tests call Gemini.

No live Gemini request was performed: the configured backend key was absent.
Mocks do not prove provider connectivity, credentials, model availability or quality.

1. Configure the key privately and an available model; restart the backend.
2. Start PostgreSQL, apply migrations and start backend/frontend as in README.
3. Visit http://127.0.0.1:5173. Existing documents should appear. Select Index
   to index a PDF without re-uploading; retries reuse existing vectors.
4. Ask one narrow question answerable from the uploaded PDF.
5. Expand Cited passages and independently compare answer claims, filename and
   page with the original PDF. Ensure citation IDs belong to returned sources.
6. Use a disposable PDF to check upload/list/index/delete; deletion requires confirmation.

Each live question may incur charges; avoid repeated smoke tests. No original PDF
viewer is provided because ingestion retains extracted text, not original bytes.
No chat persistence, streaming, hybrid retrieval, reranking or agent framework is added.
