import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import Documents from './Documents'

const doc = { id: 'd1', filename: 'ocean.pdf', status: 'ready', page_count: 2, chunk_count: 2, size_bytes: 2048, error_message: null }

it('lists index status, uploads, indexes and confirms deletion', async () => {
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'DELETE') return new Response(null, { status: 204 })
    if (path.endsWith('/index-status')) return new Response(JSON.stringify({ total_chunks: 2, indexed_chunks: 0, complete: false }))
    if (init?.method) return new Response('{}')
    return new Response(JSON.stringify([doc]))
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<Documents />)
  expect(await screen.findByText('ocean.pdf')).toBeInTheDocument()
  expect(await screen.findByText('0 of 2 passages indexed')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Index document' }))
  expect(await screen.findByText(/ready for questions/)).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith('/api/documents/d1/index', expect.objectContaining({ method: 'POST' }))

  fireEvent.change(screen.getByLabelText(/Upload a PDF/), { target: { files: [new File(['pdf'], 'new.pdf', { type: 'application/pdf' })] } })
  expect(await screen.findByText(/new.pdf uploaded/)).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith('/api/documents?filename=new.pdf', expect.objectContaining({ body: expect.any(File) }))

  fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/documents/d1', expect.objectContaining({ method: 'DELETE' })))
})

it('shows an empty state after recovering from a list failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(new Response('[]')))
  render(<Documents />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh documents' }))
  expect(await screen.findByText('No documents yet')).toBeInTheDocument()
})

it('shows a completed index as search ready', async () => {
  vi.stubGlobal('fetch', vi.fn(async (path: string) => new Response(JSON.stringify(path.endsWith('/index-status') ? { total_chunks: 2, indexed_chunks: 2, complete: true } : [doc]))))
  render(<Documents />)
  expect(await screen.findByText('Search ready')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Indexed' })).toBeDisabled()
})
