import { useState } from 'react'
import { ApiError, request } from './api/request'

type Source = { source_id: string; document_id: string; filename: string; page_number: number; chunk_index: number; text: string; cosine_distance: number }
type Answer = { status: 'answered' | 'insufficient_evidence'; answer: string; citations: string[]; sources: Source[]; unindexed_documents: number }
type SearchResult = Omit<Source, 'source_id'> & { id: string }
type SearchResponse = { results: SearchResult[] }
const providerCodes = new Set(['provider_timeout', 'provider_temporarily_unavailable', 'provider_rate_limited', 'provider_auth_failed', 'provider_unavailable', 'invalid_model_output', 'invalid_citations'])

function friendlyError(failure: unknown) {
  if (!(failure instanceof ApiError)) return 'The answer service could not be reached. Check the backend connection and try again.'
  const messages: Record<string, string> = {
    provider_timeout: 'Gemini took too long to respond. Your documents are still available—try again in a moment.',
    provider_temporarily_unavailable: 'Gemini is temporarily unavailable or under high demand. Try again later.',
    provider_rate_limited: 'Gemini is receiving too many requests. Wait a moment before trying again.',
    provider_auth_failed: 'The answer provider needs attention. Check the backend Gemini configuration.',
    provider_unavailable: 'Gemini could not complete this request. Try again later.',
    invalid_model_output: 'Gemini returned a response TraceRAG could not safely use.',
    invalid_citations: 'Gemini returned citations TraceRAG could not verify, so no answer was shown.',
    index_required: 'Your documents need to be indexed before they can answer questions.',
  }
  return failure.code && messages[failure.code] ? messages[failure.code] : failure.message
}

export default function Questions() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [fallbackSources, setFallbackSources] = useState<Source[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function ask() {
    const submitted = question.trim()
    if (!submitted || busy) return
    setBusy(true); setError(''); setAnswer(null); setFallbackSources([])
    try {
      setAnswer(await request<Answer>('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: submitted, top_k: 5 }) }))
    } catch (failure) {
      setError(friendlyError(failure))
      if (failure instanceof ApiError && failure.code && providerCodes.has(failure.code)) {
        try {
          const search = await request<SearchResponse>('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: submitted, top_k: 5 }) })
          setFallbackSources(search.results.map((source, index) => ({ ...source, source_id: `R${index + 1}` })))
        } catch { /* Preserve the original provider error; evidence fallback is best-effort. */ }
      }
    } finally { setBusy(false) }
  }

  const sources = answer?.sources ?? fallbackSources
  return <section className="panel question-panel" aria-labelledby="question-title">
    <div className="question-heading"><div><p className="section-label">Evidence workspace</p><h2 id="question-title">Ask your documents</h2><p>TraceRAG retrieves passages first, then asks Gemini to answer only from that evidence.</p></div><span className="grounded-badge">Grounded answers</span></div>
    <form className="question-form" onSubmit={event => { event.preventDefault(); void ask() }}><label htmlFor="question" className="sr-only">Your question</label><textarea id="question" value={question} maxLength={2000} required disabled={busy} placeholder="Ask a specific question about your indexed documents…" onChange={event => setQuestion(event.target.value)} /><div className="composer-footer"><span>{question.length.toLocaleString()} / 2,000</span><button className="primary-button" disabled={busy || !question.trim()}>{busy ? <><span className="spinner light" aria-hidden="true" />Working…</> : <>Ask TraceRAG <span aria-hidden="true">→</span></>}</button></div></form>
    <p className="privacy-note">Selected passages and your question are sent to Gemini. API keys stay on the backend.</p>
    {busy && <div className="answer-loading" role="status"><div className="loading-orbit" aria-hidden="true" /><div><strong>Building a grounded answer</strong><p>Retrieving relevant passages and checking citations…</p></div></div>}
    {error && <div className="answer-error" role="alert"><span aria-hidden="true">!</span><div><strong>Answer unavailable</strong><p>{error}</p>{fallbackSources.length > 0 && <p className="evidence-available">Relevant evidence was retrieved and remains available below.</p>}</div></div>}
    {!busy && !answer && !error && <div className="answer-empty"><div className="empty-illustration" aria-hidden="true">“ ”</div><strong>Start with a focused question</strong><p>Ask about methods, findings, definitions, or details in your indexed PDFs.</p></div>}
    {answer && <article className={`answer-card ${answer.status}`} aria-live="polite"><div className="answer-kicker"><span>{answer.status === 'insufficient_evidence' ? 'Evidence check' : 'Grounded answer'}</span>{answer.status === 'answered' && <span>{answer.citations.length} citation{answer.citations.length === 1 ? '' : 's'}</span>}</div><h3>{answer.status === 'insufficient_evidence' ? 'Not enough evidence' : 'Answer'}</h3><p className="answer-text">{answer.answer}</p>{answer.unindexed_documents > 0 && <p className="coverage-note">Some ready documents are not indexed and were excluded.</p>}</article>}
    {sources.length > 0 && <section className="sources" aria-labelledby="sources-title"><div className="sources-heading"><div><p className="section-label">{answer ? 'Traceable evidence' : 'Retrieved evidence'}</p><h3 id="sources-title">Sources</h3></div><span>{sources.length} passage{sources.length === 1 ? '' : 's'}</span></div><div className="source-list">{sources.map(source => {
      const cited = Boolean(answer?.citations.includes(source.source_id))
      return <details className={`source-card ${cited ? 'cited' : ''}`} key={source.source_id}><summary><span className="source-number">{source.source_id}</span><span className="source-location"><strong>{source.filename}</strong><small>Page {source.page_number} · Passage {source.chunk_index + 1}</small></span><span className="source-tag">{cited ? 'Cited' : answer ? 'Retrieved' : 'Evidence only'}</span><span className="chevron" aria-hidden="true">⌄</span></summary><div className="passage"><p>{source.text}</p></div></details>
    })}</div><p className="citation-note">Citation IDs confirm source membership, not factual correctness. Always inspect the supporting passage.</p></section>}
  </section>
}
