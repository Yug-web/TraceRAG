# Stage C: vector retrieval baseline

Persisted chunks → explicit indexing → local sentence-transformers model → pgvector.
Search → same model/profile → exact cosine-distance SQL → source metadata.
No LLM is called by the search endpoint. Hybrid ranking and reranking are not implemented.
Distance is a ranking signal, not a correctness or confidence score.

## Model and configuration

The default is sentence-transformers/all-MiniLM-L6-v2, pinned to revision
1110a243fdf4706b3f48f1d95db1a4f5529b4d41, with 384 dimensions and CPU inference.
The first use downloads public model files; document/query text stays local.
TRACERAG_EMBEDDING_LOCAL_FILES_ONLY=true requires already-cached weights. The adapter
uses safetensors and disables model-provided remote Python code. Configuration is
listed in backend/.env.example. When switching models, update the model name, revision,
dimensions, and token limit together. The loaded model is checked against these limits.
This adapter targets standard text SentenceTransformer models without prompt prefixes.

## Long inputs

MiniLM normally truncates at 256 tokens, including special tokens. Existing source
chunks are character windows and can exceed that. The adapter instead splits token
IDs into disjoint windows that fit, embeds and normalizes each window, computes a
weighted sum using the number of content tokens, and normalizes the final vector.
Each vector still corresponds to one original chunk; IDs and offsets do not change.
The policy is versioned as token-window-weighted-mean-l2-v1. Pooling can dilute a
specific relevant detail; it is a baseline to evaluate, not a claimed improvement.

## Storage and retries

Embedding profiles hash model name, immutable revision, dimensions, token limit, and
preprocessing version. Batch size does not change this mathematical policy. Search
uses only the active profile, even if several models' vectors are stored.

chunk_embeddings has a unique (chunk_id, profile_id) key. Foreign keys tie vectors to
sources and profiles; database constraints enforce vector/profile dimension agreement.
The vector column permits different dimensions in different profiles. Exact search
filters to the active profile before applying cosine distance.

Indexing reads persisted chunks and skips existing vectors. Inference happens outside
transactions. Before publishing, the service locks the document and checks that its
source snapshot is unchanged. Publication is atomic; ON CONFLICT protects concurrent
retries. Concurrent requests may repeat computation but cannot duplicate stored vectors.
Deletion cascades to embeddings and cannot resurrect a document deleted during inference.

Upload status ready still means extraction/chunking succeeded. Index coverage is
reported separately. A model failure leaves ingestion status and source text intact.
Search excludes partially indexed documents and reports corpus indexing coverage.

## Commands

After native pgvector is installed, from backend/:

```powershell
uv sync --frozen
uv run --frozen alembic upgrade head
uv run --frozen python -m app.index_documents --all
```

Replace --all with --document UUID to index one document. No re-upload is necessary.
Repeating the command skips existing embeddings. API equivalents are in api.md.

## Tests and limits

Synthetic passages about oceans and plants provide reproducible source data. Controlled
fake vectors test ranking mechanics, metadata, model separation, missing embeddings,
failures, concurrent retries, and deletion using actual PostgreSQL/pgvector queries.
They do not measure semantic retrieval quality. An opt-in real-model test checks vector
dimensions, normalization, repeatability, and long inputs. Set TRACERAG_REAL_MODEL_TESTS=1
to include it. Ordinary CI avoids model downloads but exercises actual vector SQL.

Migration 0002 enables the extension and creates embedding tables. Downgrade removes
those tables, not the potentially shared extension. Back up valuable databases before
migrations. Integration tests must use a disposable database ending in _test.

Exact search is appropriate for this small corpus. Approximate indexing needs later
scale measurements and dimension-specific indexes. Inference is synchronous and serialized
within each application process; there is no durable indexing queue, cross-process
concurrency limit, or hard inference deadline. Initial downloads and CPU inference can
be slow. No retrieval-quality scores have been established.

References: [model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
[pgvector installation and operators](https://github.com/pgvector/pgvector).
