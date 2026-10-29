export async function checkHealth(signal: AbortSignal): Promise<void> {
  const response = await fetch('/api/health', {
    signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
  })
  if (!response.ok) throw new Error(`Health request failed (${response.status})`)

  const body: unknown = await response.json()
  if (typeof body !== 'object' || body === null || !('status' in body) || body.status !== 'ok') {
    throw new Error('Unexpected health response')
  }
}
