<!--
Vue 概念：`computed` 根据 result 的运行时结构判断渲染分支。
组件只渲染经过后端校验的数据，不接受或执行模型生成的绘图代码。
-->
<script setup lang="ts">
import { computed } from 'vue'

import type { ChartArtifact } from '../types/chat'
import ChartView from './ChartView.vue'
import DataGrid from './DataGrid.vue'

const props = defineProps<{
  result: unknown
  expanded: boolean
}>()

const queryResult = computed(() => {
  const value = props.result
  if (!isRecord(value)) {
    return null
  }
  const rows = value.rows
  const columns = value.columns
  if (
    Array.isArray(rows) &&
    rows.every(isRecord) &&
    Array.isArray(columns) &&
    columns.every((column) => typeof column === 'string')
  ) {
    return {
      rows,
      columns: columns as string[],
    }
  }
  return null
})

const chartArtifact = computed<ChartArtifact | null>(() => {
  const value = props.result
  if (!isRecord(value) || value.kind !== 'chart' || !isRecord(value.spec)) {
    return null
  }
  const spec = value.spec
  if (
    typeof spec.type !== 'string' ||
    typeof spec.title !== 'string' ||
    typeof spec.x_field !== 'string' ||
    !Array.isArray(spec.y_fields) ||
    !Array.isArray(spec.data)
  ) {
    return null
  }
  return value as unknown as ChartArtifact
})

const formattedText = computed(() => {
  if (typeof props.result === 'string') {
    return props.result
  }
  return JSON.stringify(props.result, null, 2)
})

const visibleText = computed(() => {
  if (props.expanded || formattedText.value.length <= 600) {
    return formattedText.value
  }
  return `${formattedText.value.slice(0, 600)}\n…`
})

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
</script>

<template>
  <DataGrid
    v-if="queryResult"
    :rows="queryResult.rows"
    :columns="queryResult.columns"
  />
  <ChartView v-else-if="chartArtifact" :spec="chartArtifact.spec" />
  <pre v-else class="tool-text">{{ visibleText }}</pre>
</template>

<style scoped>
.tool-text {
  max-height: 320px;
  margin: 0;
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: #334155;
  background: #f8fafc;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>

