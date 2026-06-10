import { getJson, http, type PaginatedResponse } from './http'

export interface SystemConfigItem {
  url: string
  id: number
  config_type: string
  name: string
  description: string
  config_data: Record<string, unknown>
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ListSystemConfigsParams extends Record<string, unknown> {
  config_type?: string
  name?: string
  is_active?: boolean
  page?: number
}

export async function listSystemConfigs(params?: ListSystemConfigsParams) {
  return await getJson<PaginatedResponse<SystemConfigItem>>('/system-configs/', { params })
}

export async function getActiveBigParticleAlgorithmConfig(): Promise<SystemConfigItem | null> {
  const res = await listSystemConfigs({
    config_type: 'algorithm',
    name: 'big_particle',
    is_active: true,
  })
  return res.results[0] ?? null
}

export interface UpdateSystemConfigPayload {
  config_data?: Record<string, unknown>
}

export async function updateSystemConfig(
  id: number,
  payload: UpdateSystemConfigPayload,
): Promise<SystemConfigItem> {
  const res = await http.patch<SystemConfigItem>(`/system-configs/${id}/`, payload)
  return res.data
}
