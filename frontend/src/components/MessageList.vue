<!--
Vue 概念：`defineProps` 接收响应式数据，`watch` 监听消息变化，
`nextTick` 等待 DOM 更新后自动滚动到底部。
-->
<script setup lang="ts">
import { Bot, UserRound } from '@lucide/vue'
import { nextTick, ref, watch } from 'vue'

import type { ChatMessage } from '../types/chat'
import { renderMarkdown } from '../utils/markdown'

const props = defineProps<{
  messages: ChatMessage[]
  streaming: boolean
}>()

const emit = defineEmits<{
  suggest: [content: string]
}>()

const listElement = ref<HTMLElement | null>(null)
const suggestions = [
  '统计各区域的销售总额，并用柱状图展示。',
  '找出退货率最高的三个品类。',
  '分析近六个月销售额变化趋势。',
]

watch(
  () => [
    props.messages.length,
    props.messages[props.messages.length - 1]?.content,
  ],
  async () => {
    await nextTick()
    listElement.value?.scrollTo({
      top: listElement.value.scrollHeight,
      behavior: 'smooth',
    })
  },
)
</script>

<template>
  <section ref="listElement" class="message-list" aria-live="polite">
    <div v-if="!messages.length" class="message-empty">
      <div class="empty-mark"><Bot :size="24" /></div>
      <p>从一个数据问题开始</p>
      <div class="suggestion-list">
        <button
          v-for="suggestion in suggestions"
          :key="suggestion"
          type="button"
          class="suggestion"
          @click="emit('suggest', suggestion)"
        >
          {{ suggestion }}
        </button>
      </div>
    </div>

    <article
      v-for="message in messages"
      :key="message.id"
      class="message"
      :class="`message-${message.role}`"
    >
      <div class="message-avatar">
        <UserRound v-if="message.role === 'user'" :size="17" />
        <Bot v-else :size="17" />
      </div>
      <div class="message-body">
        <!-- markdown-it 已关闭原始 HTML，并会转义不可信内容。 -->
        <!-- eslint-disable vue/no-v-html -->
        <div
          v-if="message.role === 'assistant'"
          class="message-content markdown-content"
          v-html="renderMarkdown(message.content)"
        ></div>
        <!-- eslint-enable vue/no-v-html -->
        <p v-else class="message-content">
          {{ message.content || (message.status === 'streaming' ? '正在分析…' : '') }}
        </p>
        <span v-if="message.status === 'aborted'" class="message-status">已停止</span>
        <span v-else-if="message.status === 'error'" class="message-status error">执行失败</span>
      </div>
    </article>
  </section>
</template>

<style scoped>
.message-list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background:
    linear-gradient(180deg, rgb(255 255 255 / 80%), rgb(248 250 252 / 92%)),
    var(--canvas-color);
}

.message-empty {
  min-height: 100%;
  display: grid;
  place-content: center;
  justify-items: center;
  color: var(--muted-color);
}

.empty-mark {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-color);
  border-radius: 50%;
  color: var(--accent-color);
  background: var(--surface-color);
}

.message-empty p {
  margin: 14px 0 18px;
  color: var(--text-color);
  font-size: 15px;
}

.suggestion-list {
  display: grid;
  gap: 8px;
  width: min(420px, 72vw);
}

.suggestion {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-color);
  background: var(--surface-color);
  text-align: left;
  cursor: pointer;
}

.suggestion:hover {
  border-color: var(--accent-color);
}

.message {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}

.message-user {
  grid-template-columns: minmax(0, 1fr) 30px;
}

.message-user .message-avatar {
  grid-column: 2;
}

.message-user .message-body {
  grid-column: 1;
  grid-row: 1;
  justify-self: end;
  background: #e7f2f1;
}

.message-avatar {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: var(--surface-color);
  background: var(--heading-color);
}

.message-user .message-avatar {
  background: var(--accent-color);
}

.message-body {
  max-width: min(660px, 90%);
  padding: 11px 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--surface-color);
}

.message-content {
  margin: 0;
  color: var(--text-color);
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.markdown-content :deep(p) {
  margin: 0 0 10px;
}

.markdown-content :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-content :deep(table) {
  width: 100%;
  margin: 10px 0;
  border-collapse: collapse;
  font-size: 13px;
}

.markdown-content :deep(th),
.markdown-content :deep(td) {
  padding: 7px 9px;
  border: 1px solid var(--border-color);
  text-align: left;
}

.markdown-content :deep(th) {
  background: #f1f5f9;
}

.markdown-content :deep(code) {
  padding: 2px 4px;
  border-radius: 4px;
  background: #f1f5f9;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 12px;
}

.markdown-content :deep(pre) {
  max-width: 100%;
  overflow: auto;
  padding: 10px;
  border-radius: 6px;
  background: #f8fafc;
}

.message-status {
  display: inline-block;
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
}

.message-status.error {
  color: #b91c1c;
}
</style>
