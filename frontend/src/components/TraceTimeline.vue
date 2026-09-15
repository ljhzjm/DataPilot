<!--
Vue 概念：`computed` 汇总步骤和 Token；`v-if` / `v-for` 根据响应式状态
切换空状态与时间线。轨迹只展示状态，不在组件内发起请求。
-->
<script setup lang="ts">
import { Activity, CircleDot } from '@lucide/vue'
import { computed } from 'vue'

import type { AgentStep } from '../types/chat'
import TraceStep from './TraceStep.vue'

const props = defineProps<{
  steps: AgentStep[]
  streaming: boolean
  error: string | null
}>()

const totalTokens = computed(() =>
  props.steps.reduce(
    (total, step) => total + step.usage.input_tokens + step.usage.output_tokens,
    0,
  ),
)
</script>

<template>
  <section class="trace-panel">
    <header class="trace-header">
      <div>
        <span class="panel-kicker">Agent</span>
        <strong>执行轨迹</strong>
      </div>
      <div class="trace-state" :class="{ active: streaming }">
        <CircleDot :size="14" />
        {{ streaming ? '执行中' : '已就绪' }}
      </div>
    </header>

    <div class="trace-summary">
      <span><Activity :size="14" /> {{ steps.length }} 个步骤</span>
      <span>{{ totalTokens }} tokens</span>
    </div>

    <div class="trace-scroll">
      <el-alert
        v-if="error"
        type="error"
        :title="error"
        :closable="false"
        show-icon
      />
      <ol v-if="steps.length" class="trace-list">
        <TraceStep v-for="step in steps" :key="step.step" :step="step" />
      </ol>
      <div v-else class="trace-empty">
        <Activity :size="24" />
        <p>发送问题后，这里会显示工具调用过程。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.trace-panel {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto auto 1fr;
  border-left: 1px solid var(--border-color);
  background: var(--canvas-color);
}

.trace-header {
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 18px;
  border-bottom: 1px solid var(--border-color);
  background: var(--surface-color);
}

.trace-header > div:first-child {
  display: grid;
  gap: 2px;
}

.panel-kicker {
  color: var(--muted-color);
  font-size: 11px;
  text-transform: uppercase;
}

.trace-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--muted-color);
  font-size: 12px;
}

.trace-state.active {
  color: var(--accent-color);
}

.trace-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 9px 18px;
  border-bottom: 1px solid var(--border-color);
  color: var(--muted-color);
  background: #f8fafc;
  font-size: 12px;
}

.trace-summary span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.trace-scroll {
  min-height: 0;
  overflow-y: auto;
  padding: 20px 18px 28px;
}

.trace-list {
  margin: 0;
  padding: 0;
}

.trace-empty {
  min-height: 42vh;
  display: grid;
  place-content: center;
  justify-items: center;
  color: var(--muted-color);
  text-align: center;
}

.trace-empty p {
  margin: 12px 0 0;
  font-size: 13px;
}
</style>

