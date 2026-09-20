import type { UsagePage, UsageSummary } from '../types/observability'
import { apiFetch } from './client'

export async function getUsageSummary(): Promise<UsageSummary> {
  const response = await apiFetch('/api/observability/summary')
  if (!response.ok) {
    throw new Error(`读取用量统计失败：${response.status}`)
  }
  return (await response.json()) as UsageSummary
}

export async function getUsageRecords(limit = 20): Promise<UsagePage> {
  const response = await apiFetch(`/api/observability/usage?limit=${limit}`)
  if (!response.ok) {
    throw new Error(`读取调用记录失败：${response.status}`)
  }
  return (await response.json()) as UsagePage
}
