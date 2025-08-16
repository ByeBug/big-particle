import { getJson, type PaginatedResponse } from './http'

export interface VideoStreamItem {
  url: string
  id: number
  type: string
  name: string
  ip: string
  address: string
  width: number
  height: number
  fps: number | null
  actual_fps: number | null
  enabled: boolean
  status: string
  status_message: string
  save_frames: boolean
  created_at: string
  updated_at: string
}

export interface ListVideoStreamsParams extends Record<string, unknown> {
  page?: number
}

export async function listVideoStreams(params?: ListVideoStreamsParams) {
  return await getJson<PaginatedResponse<VideoStreamItem>>('/videostreams/', { params })
}
