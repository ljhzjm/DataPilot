<!--
Vue 概念：子组件通过 props 接收单个步骤，并用 ref 管理展开状态。
模板按“思考摘要 -> 工具调用 -> 工具结果 -> 指标”的顺序展示。
-->
<script setup lang="ts">
import { ChevronDown, ChevronRight, Wrench } from '@lucide/vue'
import { ref } from 'vue'

import type { AgentStep } from '../types/chat'
import ToolResultView from './ToolResultView.vue'

defineProps<{
  step: AgentStep
}>()

const expanded = ref(false)
</script>

<template>
  <li class="trace-step">
    <div class="step-rail">
      <span class="step-index">{{ step.step }}</span>
    </div>
    <div class="step-content">
      <p class="step-thought">
        {{ step.assistant_content || '模型正在选择下一步工具。' }}
      </p>

      <div
        v-for="execution in step.tool_executions"
        :key="execution.tool_call_id"
        class="tool-block"
      >
        <div class="tool-heading">
          <span class="tool-name">
            <Wrench :size="14" />
            {{ execution.tool_name }}
          </span>
          <button
            type="button"
            class="expand-button"
            :aria-label="expanded ? '收起工具结果' : '展开工具结果'"
            @click="expanded = !expanded"
          >
            <component :is="expanded ? ChevronDown : ChevronRight" :size="16" />
          </button>
        </div>

        <pre class="tool-arguments">{{ JSON.stringify(execution.arguments, null, 2) }}</pre>

        <el-alert
          v-if="execution.error"
          type="error"
          :title="execution.error"
          :closable="false"
          show-icon
        />
        <ToolResultView
          v-else
          :result="execution.result"
          :expanded="expanded"
        />

        <div class="step-meta">
          <span>{{ execution.duration_ms.toFixed(1) }} ms</span>
          <span>
            tokens
            {{ step.usage.input_tokens + step.usage.output_tokens }}
          </span>
        </div>
      </div>
    </div>
  </li>
</template>

<style scoped>
.trace-step {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 12px;
  list-style: none;
}

.step-rail {
  position: relative;
  display: flex;
  justify-content: center;
}

.step-rail::after {
  position: absolute;
  top: 30px;
  bottom: -22px;
  width: 1px;
  background: var(--border-color);
  content: '';
}

.trace-step:last-child .step-rail::after {
  display: none;
}

.step-index {
  z-index: 1;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 1px solid #b7d8d4;
  border-radius: 50%;
  color: #0f766e;
  background: #ecfdf9;
  font-size: 12px;
  font-weight: 700;
}

.step-content {
  min-width: 0;
  padding-bottom: 22px;
}

.step-thought {
  margin: 3px 0 10px;
  color: var(--text-color);
  font-size: 13px;
  line-height: 1.6;
}

.tool-block {
  padding: 11px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: #ffffff;
}

.tool-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.tool-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
}

.expand-button {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 6px;
  color: #64748b;
  background: transparent;
  cursor: pointer;
}

.expand-button:hover {
  background: #f1f5f9;
}

.tool-arguments {
  max-height: 150px;
  margin: 0 0 8px;
  overflow: auto;
  padding: 9px;
  border-radius: 6px;
  color: #475569;
  background: #f8fafc;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.step-meta {
  display: flex;
  gap: 12px;
  margin-top: 8px;
  color: var(--muted-color);
  font-size: 11px;
}
</style>

