import { useStore } from '@/store'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

export async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const token = useStore.getState().token
  const headers: HeadersInit = { 'Content-Type': 'application/json', ...(opts?.headers ?? {}) }
  if (token) (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`

  const res = await fetch(path, { ...opts, headers })
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) {
      useStore.getState().logout()
      window.location.href = '/login'
      throw new ApiError(res.status, 'Session expired — please log in again')
    }
    if (res.status === 429) throw new ApiError(429, 'Rate limited — try again later')
    if (res.status >= 500) throw new ApiError(res.status, `Server error (${res.status}) — check backend logs`)
    throw new ApiError(res.status, `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}
