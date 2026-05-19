import { useStore } from '@/store'

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const apiKey = useStore.getState().apiKey
  const headers: HeadersInit = { 'Content-Type': 'application/json', ...(opts?.headers ?? {}) }
  if (apiKey) (headers as Record<string, string>)['X-API-Key'] = apiKey

  const res = await fetch(path, { ...opts, headers })
  if (!res.ok) {
    if (res.status === 401) throw new ApiError(401, 'Unauthorized — check API key')
    if (res.status === 429) throw new ApiError(429, 'Rate limited — try again later')
    if (res.status >= 500) throw new ApiError(res.status, `Server error (${res.status}) — check backend logs`)
    throw new ApiError(res.status, `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}
