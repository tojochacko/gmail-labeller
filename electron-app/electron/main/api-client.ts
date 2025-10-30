import { URL } from 'node:url'

const DEFAULT_BASE_URL = process.env.ELECTRON_API_BASE_URL ?? 'http://localhost:8000'

const baseUrl = DEFAULT_BASE_URL.endsWith('/') ? DEFAULT_BASE_URL.slice(0, -1) : DEFAULT_BASE_URL

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

interface RequestOptions extends RequestInit {
  searchParams?: Record<string, string | number | boolean | undefined>
}

export class ApiClient {
  constructor(private readonly base: string = baseUrl) {}

  async request<T = unknown>(path: string, options: RequestOptions = {}): Promise<T> {
    const url = new URL(path, this.base)

    if (options.searchParams) {
      Object.entries(options.searchParams).forEach(([key, value]) => {
        if (value === undefined) return
        url.searchParams.set(key, String(value))
      })
    }

    const headers = {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers ?? {}),
    }

    const response = await fetch(url.toString(), {
      method: (options.method ?? 'GET') as HttpMethod,
      ...options,
      headers,
    })

    if (!response.ok) {
      const text = await response.text()
      throw new Error(`Backend request failed (${response.status}): ${text}`)
    }

    if (response.status === 204) {
      return undefined as T
    }

    const contentType = response.headers.get('content-type') ?? ''
    if (contentType.includes('application/json')) {
      return (await response.json()) as T
    }

    return (await response.text()) as T
  }
}

export const apiClient = new ApiClient()
