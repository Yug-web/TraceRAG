import { useEffect, useState } from 'react'
import { request } from './api/request'

type Document = { id: string; filename: string; status: 'processing' | 'ready' | 'failed'; page_count: number; chunk_count: number; size_bytes: number; error_message: string | null }
type IndexStatus = { total_chunks: number; indexed_chunks: number; complete: boolean }
type Operation = { kind: 'upload' | 'index' | 'delete'; id?: string; label: string } | null

function formatBytes(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function Documents() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [indexes, setIndexes] = useState<Record<string, IndexStatus>>({})
  const [offset, setOffset] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const [operation, setOperation] = useState<Operation>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [confirm, setConfirm] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    request<Document[]>(`/api/documents?limit=20&offset=${offset}`, { signal: controller.signal })
      .then(async rows => {
        if (!active) return
        setDocuments(rows)
        const results = await Promise.allSettled(rows.filter(row => row.status === 'ready').map(async row => [row.id, await request<IndexStatus>(`/api/documents/${row.id}/index-status`, { signal: controller.signal })] as const))
        if (!active) return
        setIndexes(Object.fromEntries(results.flatMap(result => result.status === 'fulfilled' ? [result.value] : [])))
        setLoading(false)
      })
      .catch(failure => {
        if (!active || failure instanceof DOMException && failure.name === 'AbortError') return
        setError('Could not load documents. Check the backend connection and try again.')
        setLoading(false)
      })
    return () => { active = false; controller.abort() }
  }, [offset, refresh])

  function reload() { setLoading(true); setError(''); setNotice(''); setRefresh(value => value + 1) }
  async function act(current: NonNullable<Operation>, action: () => Promise<unknown>, message: string) {
    if (operation) return
    setOperation(current); setError(''); setNotice('')
    try { await action(); setNotice(message) }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Document operation failed.') }
    finally { setOperation(null); setConfirm(null); setLoading(true); setRefresh(value => value + 1) }
  }

  return <section className="panel documents-panel" aria-labelledby="documents-title">
    <div className="panel-heading"><div><p className="section-label">Library</p><h2 id="documents-title">Documents</h2></div><button className="icon-button" type="button" disabled={Boolean(operation) || loading} onClick={reload} aria-label="Refresh documents">↻</button></div>
    <label className={`upload-zone ${operation?.kind === 'upload' ? 'is-busy' : ''}`} htmlFor="pdf"><span className="upload-icon" aria-hidden="true">↑</span><span><strong>{operation?.kind === 'upload' ? `Uploading ${operation.label}…` : 'Upload a PDF'}</strong><small>Text-based PDF · up to 10 MB</small></span><input id="pdf" type="file" accept="application/pdf,.pdf" disabled={Boolean(operation)} onChange={event => {
      const file = event.target.files?.[0]; event.target.value = ''
      if (file) void act({ kind: 'upload', label: file.name }, () => request(`/api/documents?filename=${encodeURIComponent(file.name)}`, { method: 'POST', headers: { 'Content-Type': 'application/pdf' }, body: file }), `${file.name} uploaded. Index it to make it searchable.`)
    }} /></label>
    {operation && <div className="inline-status" role="status"><span className="spinner" aria-hidden="true" />{operation.kind === 'index' ? `Indexing ${operation.label}…` : operation.kind === 'delete' ? `Deleting ${operation.label}…` : 'Extracting pages and passages…'}</div>}
    {error && <div className="notice error" role="alert">{error}</div>}{notice && <div className="notice success" role="status">{notice}</div>}
    {loading && <div className="document-skeleton" aria-label="Loading documents"><span /><span /></div>}
    {!loading && !documents.length && <div className="empty-state"><span aria-hidden="true">□</span><strong>No documents yet</strong><p>Upload a PDF to create your research library.</p></div>}
    <ul className="document-list">{documents.map(doc => {
      const index = indexes[doc.id]
      return <li className="document-card" key={doc.id}><div className="document-icon" aria-hidden="true">PDF</div><div className="document-content"><div className="document-title-row"><strong title={doc.filename}>{doc.filename}</strong><span className={`status-badge ${doc.status}`}>{doc.status}</span></div><p className="document-meta">{doc.page_count} pages · {doc.chunk_count} passages · {formatBytes(doc.size_bytes)}</p>
        {doc.status === 'ready' && <div className="index-state"><span className={`index-dot ${index?.complete ? 'complete' : ''}`} aria-hidden="true" />{index ? index.complete ? 'Search ready' : `${index.indexed_chunks} of ${index.total_chunks} passages indexed` : 'Checking index…'}</div>}
        {doc.status === 'failed' && doc.error_message && <p className="document-error">{doc.error_message}</p>}
        <div className="document-actions"><button className="secondary-button" disabled={Boolean(operation) || doc.status !== 'ready' || index?.complete} onClick={() => void act({ kind: 'index', id: doc.id, label: doc.filename }, () => request(`/api/documents/${doc.id}/index`, { method: 'POST' }), `${doc.filename} is ready for questions.`)}>{operation?.id === doc.id && operation.kind === 'index' ? 'Indexing…' : index?.complete ? 'Indexed' : 'Index document'}</button>
          {confirm === doc.id ? <div className="confirm-actions" role="group" aria-label={`Confirm deletion of ${doc.filename}`}><button className="danger-button" disabled={Boolean(operation)} onClick={() => void act({ kind: 'delete', id: doc.id, label: doc.filename }, () => request(`/api/documents/${doc.id}`, { method: 'DELETE' }), `${doc.filename} deleted.`)}>Delete permanently</button><button className="text-button" onClick={() => setConfirm(null)}>Cancel</button></div> : <button className="text-button danger-text" disabled={Boolean(operation)} onClick={() => setConfirm(doc.id)}>Delete</button>}
        </div></div></li>
    })}</ul>
    {(offset > 0 || documents.length === 20) && <nav className="pagination" aria-label="Document pages"><button className="text-button" disabled={Boolean(operation) || loading || offset === 0} onClick={() => { setLoading(true); setOffset(value => Math.max(0, value - 20)) }}>Previous</button><span>Page {offset / 20 + 1}</span><button className="text-button" disabled={Boolean(operation) || loading || documents.length < 20} onClick={() => { setLoading(true); setOffset(value => value + 20) }}>Next</button></nav>}
  </section>
}
