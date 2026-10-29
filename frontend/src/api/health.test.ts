import { expect, it, vi } from 'vitest'
import { checkHealth } from './health'

it.each([
  new Response('failure', { status: 503 }),
  new Response('<html>not JSON</html>'),
  new Response(JSON.stringify({ status: 'degraded' })),
  new Response('null'),
])('rejects HTTP errors and unexpected payloads', async response => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
  await expect(checkHealth(new AbortController().signal)).rejects.toThrow()
})

it('bounds requests with a five-second timeout', async () => {
  const timeout = new AbortController()
  const timeoutSpy = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(timeout.signal)
  vi.stubGlobal('fetch', vi.fn((_url, options: RequestInit) => new Promise((_resolve, reject) => {
    options.signal?.addEventListener('abort', () => reject(options.signal?.reason))
  })))
  const assertion = expect(checkHealth(new AbortController().signal)).rejects.toThrow('Timed out')
  timeout.abort(new DOMException('Timed out', 'TimeoutError'))
  await assertion
  expect(timeoutSpy).toHaveBeenCalledWith(5000)
})

it('propagates cancellation when the component unmounts', async () => {
  const controller = new AbortController()
  vi.stubGlobal('fetch', vi.fn((_url, options: RequestInit) => new Promise((_resolve, reject) => {
    options.signal?.addEventListener('abort', () => reject(options.signal?.reason))
  })))
  const assertion = expect(checkHealth(controller.signal)).rejects.toThrow()
  controller.abort()
  await assertion
})
