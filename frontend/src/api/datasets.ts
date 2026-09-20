import type { Dataset, DatasetSummary } from '../types/dataset'
import { apiFetch, apiRequest } from './client'

interface ApiErrorBody {
  detail?: string
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(body.detail || `请求失败：${response.status}`)
  }
  return (await response.json()) as T
}

export async function listDatasets(): Promise<DatasetSummary[]> {
  return apiRequest<DatasetSummary[]>('/api/datasets')
}

export async function uploadDataset(file: File): Promise<Dataset> {
  const formData = new FormData()
  formData.append('file', file)
  return parseResponse<Dataset>(
    await apiFetch('/api/datasets/upload', {
      method: 'POST',
      body: formData,
    }),
  )
}

export async function deleteDataset(datasetId: string): Promise<void> {
  const response = await apiFetch(`/api/datasets/${datasetId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(body.detail || `删除失败：${response.status}`)
  }
}
