import { getJson } from './http'

export interface BigParticleDailyRangeStat {
  range: string
  count: number
  percentage: number
}

export interface BigParticleDailyItem {
  stream_id: number
  date: string
  size_ranges: BigParticleDailyRangeStat[]
  total: number
}

export interface BigParticleDailyStatsResponse {
  stream_id: number
  start_date: string
  end_date: string
  daily_stats: BigParticleDailyItem[]
}

export interface GetBigParticleDailyStatsParams {
  stream_id: number | string
  start_date: string
  end_date: string
}

export async function getBigParticleDailyStats(params: GetBigParticleDailyStatsParams) {
  const p: Record<string, unknown> = { ...params }
  return await getJson<BigParticleDailyStatsResponse>('/big-particle-daily-stats/', {
    params: p,
  })
}
