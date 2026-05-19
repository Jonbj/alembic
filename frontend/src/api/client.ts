import { useStore } from '@/store'

export async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const apiKey = useStore.getState().apiKey
  const headers: HeadersInit = { 'Content-Type': 'application/json', ...(opts?.headers ?? {}) }
  if (apiKey) (headers as Record<string, string>)['X-API-Key'] = apiKey

  const res = await fetch(path, { ...opts, headers })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}
