<!--
Vue 概念：`watch` 监听抽屉打开状态并按需加载数据，避免组件挂载时请求接口；
`computed` 用于格式化成本和 Token 等展示值。
-->
<script setup lang="ts">
import { Activity, CircleDollarSign, Clock3, Cpu, RefreshCw, TriangleAlert } from '@lucide/vue'
import { computed, ref, watch } from 'vue'

import { getUsageRecords, getUsageSummary } from '../api/observability'
import type { UsageRecord, UsageSummary } from '../types/observability'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const summary = ref<UsageSummary | null>(null)
const records = ref<UsageRecord[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const formattedCost = computed(() => `$${(summary.value?.estimated_cost_usd ?? 0).toFixed(6)}`)

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      void load()
    }
  },
)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [summaryResult, usageResult] = await Promise.all([
      getUsageSummary(),
      getUsageRecords(20),
    ])
    summary.value = summaryResult
    records.value = usageResult.items
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    loading.value = false
  }
}

function formatLatency(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(0)} ms`
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    title="模型用量"
    size="420px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="usage-toolbar">
      <span>最近 24 小时全部调用</span>
      <el-button
        :icon="RefreshCw"
        circle
        aria-label="刷新用量"
        :loading="loading"
        @click="load"
      />
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <div v-if="summary" class="metric-grid">
      <article class="metric-item">
        <Cpu :size="16" />
        <span>调用次数</span>
        <strong>{{ summary.call_count }}</strong>
      </article>
      <article class="metric-item">
        <Activity :size="16" />
        <span>总 Tokens</span>
        <strong>{{ summary.total_tokens.toLocaleString() }}</strong>
      </article>
      <article class="metric-item">
        <CircleDollarSign :size="16" />
        <span>估算成本</span>
        <strong>{{ formattedCost }}</strong>
      </article>
      <article class="metric-item">
        <Clock3 :size="16" />
        <span>平均延迟</span>
        <strong>{{ formatLatency(summary.average_latency_ms) }}</strong>
      </article>
      <article class="metric-item warning">
        <TriangleAlert :size="16" />
        <span>失败调用</span>
        <strong>{{ summary.error_count }}</strong>
      </article>
    </div>

    <el-skeleton v-if="loading && !records.length" :rows="6" animated />
    <el-table v-else :data="records" size="small" max-height="520">
      <el-table-column prop="model" label="模型" min-width="130" />
      <el-table-column prop="task" label="任务" width="90" />
      <el-table-column label="Tokens" width="110">
        <template #default="{ row }">
          {{ row.input_tokens + row.output_tokens }}
        </template>
      </el-table-column>
      <el-table-column label="延迟" width="90">
        <template #default="{ row }">{{ formatLatency(row.latency_ms) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="70">
        <template #default="{ row }">
          <el-tag :type="row.success ? 'success' : 'danger'" size="small">
            {{ row.success ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </el-drawer>
</template>

<style scoped>
.usage-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  color: var(--muted-color);
  font-size: 12px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 18px;
}

.metric-item {
  min-height: 82px;
  display: grid;
  grid-template-columns: auto 1fr;
  align-content: center;
  gap: 4px 7px;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: #0f766e;
}

.metric-item span {
  color: var(--muted-color);
  font-size: 12px;
}

.metric-item strong {
  grid-column: 1 / -1;
  color: var(--text-color);
  font-size: 17px;
}

.metric-item.warning {
  color: #b45309;
}
</style>

