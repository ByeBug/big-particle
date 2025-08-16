import axios, { type AxiosInstance } from 'axios'

const DEFAULT_BASE_URL = 'http://127.0.0.1:8000'
const apiBaseUrl: string = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL

export const http: AxiosInstance = axios.create({
  baseURL: apiBaseUrl,
  headers: { Accept: 'application/json' },
  timeout: 2000,
})

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface GetJsonOptions {
  params?: Record<string, unknown>
  signal?: AbortSignal
  headers?: Record<string, string>
}

export async function getJson<T>(path: string, options: GetJsonOptions = {}): Promise<T> {
  const { params, signal, headers } = options
  const res = await http.get<T>(path, { params, signal, headers })
  return res.data
}
