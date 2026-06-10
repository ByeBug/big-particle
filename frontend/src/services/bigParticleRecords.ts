import { getJson, type PaginatedResponse } from './http'

export interface BigParticleRecordItem {
  id: number
  stream_id: number
  stream_name: string
  min_size: number
  max_size: number
  detected_at: string
  original_image_url: string
  rendered_image_url: string
}

export interface ListBigParticleRecordsParams extends Record<string, unknown> {
  stream_ids?: number[] | string
  start_time?: string
  end_time?: string
  min_size?: number
  max_size?: number
  page?: number
}

export async function listBigParticleRecords(params?: ListBigParticleRecordsParams) {
  const p: Record<string, unknown> = { ...params }
  if (Array.isArray(params?.stream_ids)) {
    p.stream_ids = params?.stream_ids.join(',')
  }
  return await getJson<PaginatedResponse<BigParticleRecordItem>>('/big-particle-records/', {
    params: p,
  })
}
