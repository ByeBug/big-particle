import axios, { type AxiosInstance } from 'axios'

const DEV_BASE_URL = 'http://127.0.0.1:8000'
// const DEV_BASE_URL = '/api'    // 需要开发服务器做转发
const apiBaseUrl: string = import.meta.env.DEV ? DEV_BASE_URL : `${window.location.origin}/api`

export const http: AxiosInstance = axios.create({
  baseURL: apiBaseUrl,
  headers: { Accept: 'application/json' },
  timeout: 4000,
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
