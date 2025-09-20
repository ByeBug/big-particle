import { getJson } from './http'

export interface BigParticleHourlyRangeStat {
  range: string
  count: number
  percentage: number
}

export interface BigParticleHourlyItem {
  stream_id: number
  hour: string
  size_ranges: BigParticleHourlyRangeStat[]
  total: number
}

export interface BigParticleHourlyStatsResponse {
  stream_id: number
  date: string
  hourly_stats: BigParticleHourlyItem[]
}

export interface GetBigParticleHourlyStatsParams {
  stream_id: number | string
  date: string
}

export async function getBigParticleHourlyStats(params: GetBigParticleHourlyStatsParams) {
  const p: Record<string, unknown> = { ...params }
  return await getJson<BigParticleHourlyStatsResponse>('/big-particle-hourly-stats/', {
    params: p,
  })
}
