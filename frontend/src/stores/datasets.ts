import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  deleteDataset as deleteDatasetRequest,
  listDatasets,
  uploadDataset as uploadDatasetRequest,
} from '../api/datasets'
import type { DatasetSummary } from '../types/dataset'

export const useDatasetStore = defineStore('datasets', () => {
  const datasets = ref<DatasetSummary[]>([])
  const loading = ref(false)
  const uploading = ref(false)
  const error = ref<string | null>(null)

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      datasets.value = await listDatasets()
    } catch (cause) {
      error.value = toErrorMessage(cause)
    } finally {
      loading.value = false
    }
  }

  async function upload(file: File): Promise<void> {
    uploading.value = true
    error.value = null
    try {
      await uploadDatasetRequest(file)
      await load()
    } catch (cause) {
      error.value = toErrorMessage(cause)
    } finally {
      uploading.value = false
    }
  }

  async function remove(datasetId: string): Promise<void> {
    error.value = null
    try {
      await deleteDatasetRequest(datasetId)
      datasets.value = datasets.value.filter((dataset) => dataset.id !== datasetId)
    } catch (cause) {
      error.value = toErrorMessage(cause)
    }
  }

  return {
    datasets,
    loading,
    uploading,
    error,
    load,
    upload,
    remove,
  }
})

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

