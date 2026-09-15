<!--
Vue 概念：`v-model` 用于父组件控制抽屉状态；文件输入使用 ref 访问原生 DOM；
Pinia store 统一管理上传状态、错误和数据集列表。
-->
<script setup lang="ts">
import { Table2, Trash2, Upload } from '@lucide/vue'
import { onMounted, ref } from 'vue'

import { useDatasetStore } from '../stores/datasets'

defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const store = useDatasetStore()
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(() => {
  void store.load()
})

async function handleFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    await store.upload(file)
  }
  input.value = ''
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    title="数据表"
    size="360px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="dataset-actions">
      <input
        ref="fileInput"
        class="file-input"
        type="file"
        accept=".csv,.tsv,.xlsx"
        @change="handleFileChange"
      />
      <el-button
        type="primary"
        :icon="Upload"
        :loading="store.uploading"
        @click="fileInput?.click()"
      >
        上传 CSV / Excel
      </el-button>
      <span>单文件不超过 20 MB</span>
    </div>

    <el-alert
      v-if="store.error"
      type="error"
      :title="store.error"
      :closable="false"
      show-icon
    />

    <el-skeleton v-if="store.loading" :rows="4" animated />

    <div v-else-if="!store.datasets.length" class="dataset-empty">
      <Table2 :size="24" />
      <p>还没有已登记的数据表</p>
    </div>

    <div v-else class="dataset-list">
      <article v-for="dataset in store.datasets" :key="dataset.id" class="dataset-item">
        <div class="dataset-icon"><Table2 :size="17" /></div>
        <div class="dataset-info">
          <strong>{{ dataset.name }}</strong>
          <span>{{ dataset.table_name }}</span>
          <small>
            {{ dataset.row_count ?? 0 }} 行 · {{ formatFileSize(dataset.file_size) }}
          </small>
        </div>
        <el-tooltip content="删除数据表" placement="left">
          <el-button
            text
            :icon="Trash2"
            aria-label="删除数据表"
            @click="store.remove(dataset.id)"
          />
        </el-tooltip>
      </article>
    </div>
  </el-drawer>
</template>

<style scoped>
.dataset-actions {
  display: grid;
  gap: 8px;
  margin-bottom: 18px;
}

.dataset-actions span {
  color: var(--muted-color);
  font-size: 12px;
}

.file-input {
  display: none;
}

.dataset-empty {
  min-height: 180px;
  display: grid;
  place-content: center;
  justify-items: center;
  color: var(--muted-color);
}

.dataset-empty p {
  margin: 10px 0 0;
  font-size: 13px;
}

.dataset-list {
  display: grid;
  gap: 8px;
}

.dataset-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 32px;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.dataset-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: #0f766e;
  background: #ecfdf9;
}

.dataset-info {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.dataset-info strong {
  color: var(--text-color);
  font-size: 13px;
}

.dataset-info span,
.dataset-info small {
  overflow: hidden;
  color: var(--muted-color);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

