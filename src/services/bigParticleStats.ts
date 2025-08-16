import { getJson } from './http'

export interface BigParticleLevelCount {
  level: number
  count: number
}

export interface BigParticleRangeStats {
  range: string
  values: BigParticleLevelCount[]
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
