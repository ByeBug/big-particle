import { getJson } from './http'

export interface BigParticleLevelStat {
  level: number
  count: number
  percentage: number
}

export interface BigParticleRangeStats {
  range: string
  values: BigParticleLevelStat[]
}

export interface BigParticleStreamStats {
  stream_id: number
  stats: BigParticleRangeStats[]
}

export interface BigParticleStatsResponse {
  results: BigParticleStreamStats[]
}

export async function getBigParticleStats(streamIds: number[] | string) {
  const streamIdsParam = Array.isArray(streamIds) ? streamIds.join(',') : streamIds
  return await getJson<BigParticleStatsResponse>('/big-particle-stats/', {
    params: { stream_ids: streamIdsParam },
  })
}
