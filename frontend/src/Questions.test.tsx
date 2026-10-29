import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import Questions from './Questions'

const source = { source_id: 'S1', id: 'chunk', document_id: 'doc', filename: 'ocean.pdf', page_number: 2, chunk_index: 0, text: 'Evidence passage', cosine_distance: 0.1 }

it('shows loading, prevents duplicates, and renders expandable citations', async () => {
  let resolve!: (value: Response) => void
  const fetchMock = vi.fn(() => new Promise<Response>(done => { resolve = done }))
  vi.stubGlobal('fetch', fetchMock)
  render(<Questions />)
  const button = screen.getByRole('button', { name: /Ask TraceRAG/ })
  expect(button).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'Ocean?' } })
  fireEvent.click(button)
  fireEvent.submit(screen.getByRole('button', { name: 'Working…' }).closest('form')!)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('status')).toHaveTextContent('Building a grounded answer')
  resolve(new Response(JSON.stringify({ status: 'answered', answer: 'Currents carry heat.', citations: ['S1'], sources: [source], unindexed_documents: 0 })))
  expect(await screen.findByText('Currents carry heat.')).toBeInTheDocument()
  const summary = screen.getByText('ocean.pdf').closest('summary')!
  fireEvent.click(summary)
  expect(screen.getByText('Evidence passage').closest('details')).toHaveAttribute('open')
})

it('shows the insufficient-evidence state without fabricating sources', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'insufficient_evidence', answer: 'Not enough evidence.', citations: [], sources: [], unindexed_documents: 0 }))))
  render(<Questions />)
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'Question?' } })
  fireEvent.click(screen.getByRole('button', { name: /Ask TraceRAG/ }))
  expect(await screen.findByText('Not enough evidence', { selector: 'h3' })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
})

it.each([
  ['provider_timeout', 504, 'took too long'],
  ['provider_temporarily_unavailable', 503, 'temporarily unavailable'],
  ['provider_rate_limited', 429, 'too many requests'],
])('shows a safe %s message and retrieved evidence', async (code, status, message) => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code, message: 'server-safe message' } }), { status }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ results: [{ ...source, source_id: undefined }] })))
  vi.stubGlobal('fetch', fetchMock)
  render(<Questions />)
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'Question?' } })
  fireEvent.click(screen.getByRole('button', { name: /Ask TraceRAG/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent(message)
  expect(screen.queryByText('Grounded answer')).not.toBeInTheDocument()
  expect(await screen.findByText('Evidence passage')).toBeInTheDocument()
  expect(screen.getByText('Evidence only')).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(2)
})
