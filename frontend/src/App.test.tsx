import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import App from './App'
vi.mock('./Documents', () => ({ default: () => null }))

it('shows pending state and then confirms a healthy backend', async () => {
  let respond!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { respond = resolve })))
  render(<App />)
  expect(screen.getByRole('status')).toHaveTextContent('Checking backend connection')
  expect(screen.getByRole('button', { name: 'Checking…' })).toBeDisabled()
  respond(new Response(JSON.stringify({ status: 'ok' })))
  expect(await screen.findByText('Backend connected')).toBeInTheDocument()
})

it('allows recovery after a network failure', async () => {
  const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError('Network error'))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' })))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  expect(await screen.findByText('Backend unavailable')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
  expect(await screen.findByText('Backend connected')).toBeInTheDocument()
})
