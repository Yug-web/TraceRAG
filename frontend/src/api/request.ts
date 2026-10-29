type ErrorEnvelope = { detail?: { code?: unknown; message?: unknown } }

export class ApiError extends Error {
  status: number
  code: string | null

  constructor(status: number, code: string | null, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, signal: init.signal ?? AbortSignal.timeout(180000) })
  if (!response.ok) {
    const data: ErrorEnvelope | null = await response.json().catch(() => null)
    const code = typeof data?.detail?.code === 'string' ? data.detail.code : null
    const message = typeof data?.detail?.message === 'string'
      ? data.detail.message
      : `Request failed (${response.status}).`
    throw new ApiError(response.status, code, message)
  }
  return response.status === 204 ? undefined as T : response.json()
}
