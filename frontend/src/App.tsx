import { useEffect, useState } from 'react'
import Documents from './Documents'
import Questions from './Questions'
import { checkHealth } from './api/health'
import './App.css'

type Connection = 'checking' | 'connected' | 'unavailable'

export default function App() {
  const [connection, setConnection] = useState<Connection>('checking')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    checkHealth(controller.signal).then(
      () => { if (active) setConnection('connected') },
      () => { if (active) setConnection('unavailable') },
    )
    return () => { active = false; controller.abort() }
  }, [attempt])

  const messages = { checking: 'Checking backend connection…', connected: 'Backend connected', unavailable: 'Backend unavailable' }
  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="#workspace" aria-label="TraceRAG home"><span className="brand-mark" aria-hidden="true">T</span><span>TraceRAG<small>Evidence-first research</small></span></a><div className="connection-area"><div className={`connection ${connection}`} role="status" aria-live="polite"><span className="indicator" aria-hidden="true" />{messages[connection]}</div><button className="connection-button" disabled={connection === 'checking'} onClick={() => { setConnection('checking'); setAttempt(value => value + 1) }}>{connection === 'checking' ? 'Checking…' : 'Check again'}</button></div></header>
    <main id="workspace" className="workspace">
      <section className="workspace-intro"><div><p className="eyebrow">Your research workspace</p><h1>Answers you can trace<br />back to the page.</h1></div><p>Upload source material, index its passages, and ask grounded questions with evidence you can inspect.</p></section>
      {connection === 'unavailable' && <div className="backend-warning" role="alert"><span aria-hidden="true">!</span><div><strong>The backend is unavailable</strong><p>Start the API on port 8000, then check the connection again.</p></div></div>}
      <div className="workspace-grid"><aside><Documents /></aside><Questions /></div>
    </main>
    <footer><span>TraceRAG · Local research workspace</span><span>Answers are constrained to retrieved evidence, but still require review.</span></footer>
  </div>
}
