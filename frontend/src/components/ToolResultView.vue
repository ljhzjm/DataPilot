<!--
Vue 概念：`computed` 根据 result 的运行时结构判断渲染分支。
组件只渲染经过后端校验的数据，不接受或执行模型生成的绘图代码。
-->
<script setup lang="ts">
import { Download, FileText } from '@lucide/vue'
import { computed, defineAsyncComponent } from 'vue'

import type { ArtifactView, ChartArtifact } from '../types/chat'
import DataGrid from './DataGrid.vue'

const ChartView = defineAsyncComponent(() => import('./ChartView.vue'))

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

const pythonArtifacts = computed<{
  stdout: string
  stderr: string
  artifacts: ArtifactView[]
} | null>(() => {
  const value = props.result
  if (
    !isRecord(value) ||
    typeof value.stdout !== 'string' ||
    typeof value.stderr !== 'string' ||
    !Array.isArray(value.artifacts)
  ) {
    return null
  }
  const artifacts = value.artifacts.filter(isArtifact)
  return {
    stdout: value.stdout,
    stderr: value.stderr,
    artifacts,
  }
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

function isArtifact(value: unknown): value is ArtifactView {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.filename === 'string' &&
    typeof value.mime_type === 'string' &&
    typeof value.size === 'number' &&
    typeof value.url === 'string'
  )
}

function isImageArtifact(artifact: ArtifactView): boolean {
  return artifact.mime_type === 'image/png'
}

function formatBytes(size: number): string {
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<template>
  <DataGrid
    v-if="queryResult"
    :rows="queryResult.rows"
    :columns="queryResult.columns"
  />
  <ChartView v-else-if="chartArtifact" :spec="chartArtifact.spec" />
  <div v-else-if="pythonArtifacts" class="python-result">
    <pre v-if="pythonArtifacts.stdout" class="tool-text">{{ pythonArtifacts.stdout }}</pre>
    <pre v-if="pythonArtifacts.stderr" class="tool-text error-text">
{{ pythonArtifacts.stderr }}</pre
    >
    <div v-if="pythonArtifacts.artifacts.length" class="artifact-list">
      <div
        v-for="artifact in pythonArtifacts.artifacts"
        :key="artifact.id"
        class="artifact-item"
      >
        <a
          v-if="isImageArtifact(artifact)"
          :href="artifact.url"
          target="_blank"
          rel="noopener"
          class="artifact-image"
        >
          <img :src="artifact.url" :alt="artifact.filename" />
        </a>
        <a
          v-else
          :href="artifact.url"
          :download="artifact.filename"
          class="artifact-link"
        >
          <FileText :size="16" />
          <span>{{ artifact.filename }}</span>
          <small>{{ formatBytes(artifact.size) }}</small>
          <Download :size="15" />
        </a>
      </div>
    </div>
  </div>
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

.python-result {
  display: grid;
  gap: 8px;
}

.error-text {
  color: #b91c1c;
  background: #fef2f2;
}

.artifact-list {
  display: grid;
  gap: 8px;
}

.artifact-image {
  display: block;
  overflow: hidden;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: #ffffff;
}

.artifact-image img {
  width: 100%;
  max-height: 420px;
  display: block;
  object-fit: contain;
}

.artifact-link {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto 18px;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 0 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: #0f766e;
  background: #f8fafc;
  font-size: 12px;
  text-decoration: none;
}

.artifact-link span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-link small {
  color: var(--muted-color);
}
</style>
