import { getJson, type PaginatedResponse } from './http'

export interface AlarmData {
  size_level: string
  count?: number
  error_count?: number
  percentage?: number
  error_percentage?: number
}

export interface AlarmItem {
  id: number
  alarm_type: string
  stream_id: number
  stream_name: string
  alarm_time: string
  data: AlarmData
  record_id: number
  alarm_image_url: string
  original_image_url: string
  alarm_video_url: string | null
  created_at: string
  updated_at: string
}

export interface ListAlarmsParams extends Record<string, unknown> {
  stream_ids?: number[] | string
  alarm_type?: string
  start_time?: string
  end_time?: string
  page?: number
}

export async function listAlarms(params?: ListAlarmsParams) {
  const p: Record<string, unknown> = { ...params }
  if (Array.isArray(params?.stream_ids)) {
    p.stream_ids = params.stream_ids.join(',')
  }
  return await getJson<PaginatedResponse<AlarmItem>>('/alarms/', { params: p })
}
