<!--
Vue 概念：`computed` 根据 props 派生列定义，避免在模板中重复计算。
Element Plus 表格只负责展示，不接收或执行模型生成的代码。
-->
<script setup lang="ts">
import { Download } from '@lucide/vue'
import { computed } from 'vue'

import {
  createCsv,
  downloadTextFile,
  exportTimestamp,
} from '../utils/export'

const props = defineProps<{
  rows: Record<string, unknown>[]
  columns?: string[]
}>()

const columnNames = computed(() => {
  if (props.columns?.length) {
    return props.columns
  }
  const names = new Set<string>()
  props.rows.forEach((row) => Object.keys(row).forEach((key) => names.add(key)))
  return [...names]
})

function displayValue(value: unknown): string {
  if (value === null) {
    return 'null'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function exportCsv(): void {
  const csv = createCsv(props.rows, columnNames.value)
  downloadTextFile(
    `\ufeff${csv}`,
    `datapilot-result-${exportTimestamp()}.csv`,
    'text/csv;charset=utf-8',
  )
}
</script>

<template>
  <div class="data-grid-shell">
    <div class="grid-toolbar">
      <span>{{ rows.length }} 行</span>
      <el-tooltip content="导出 CSV" placement="left">
        <el-button
          text
          :icon="Download"
          :disabled="!rows.length"
          aria-label="导出 CSV"
          @click="exportCsv"
        />
      </el-tooltip>
    </div>
    <el-table class="data-grid" :data="rows" stripe size="small" max-height="320">
      <el-table-column
        v-for="column in columnNames"
        :key="column"
        :prop="column"
        :label="column"
        min-width="120"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          {{ displayValue(row[column]) }}
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.data-grid-shell {
  display: grid;
  gap: 6px;
}

.grid-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  color: var(--muted-color);
  font-size: 11px;
}

.data-grid {
  width: 100%;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}
</style>
