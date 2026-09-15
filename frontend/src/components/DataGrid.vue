<!--
Vue 概念：`computed` 根据 props 派生列定义，避免在模板中重复计算。
Element Plus 表格只负责展示，不接收或执行模型生成的代码。
-->
<script setup lang="ts">
import { computed } from 'vue'

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
</script>

<template>
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
</template>

<style scoped>
.data-grid {
  width: 100%;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}
</style>

