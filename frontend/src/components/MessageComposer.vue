<!--
Vue 概念：`defineProps` / `defineEmits` 用于父子组件通信；
`ref` 保存输入框的本地状态，事件修饰符 `.prevent` 阻止默认换行行为。
-->
<script setup lang="ts">
import { ArrowUp, Square } from '@lucide/vue'
import { ref } from 'vue'

const props = defineProps<{
  streaming: boolean
}>()

const emit = defineEmits<{
  send: [content: string]
  stop: []
}>()

const content = ref('')

function submit(): void {
  const value = content.value.trim()
  if (!value || props.streaming) {
    return
  }
  emit('send', value)
  content.value = ''
}
</script>

<template>
  <form class="composer" @submit.prevent="submit">
    <el-input
      v-model="content"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 6 }"
      placeholder="输入数据分析问题"
      resize="none"
      :disabled="streaming"
      @keydown.enter.exact.prevent="submit"
    />
    <el-button
      v-if="streaming"
      class="composer-action stop-action"
      :icon="Square"
      circle
      aria-label="停止生成"
      @click="emit('stop')"
    />
    <el-button
      v-else
      class="composer-action"
      type="primary"
      :icon="ArrowUp"
      circle
      native-type="submit"
      :disabled="!content.trim()"
      aria-label="发送问题"
    />
  </form>
</template>

<style scoped>
.composer {
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 14px 18px 18px;
  border-top: 1px solid var(--border-color);
  background: var(--surface-color);
}

.composer :deep(.el-textarea) {
  flex: 1;
}

.composer :deep(.el-textarea__inner) {
  min-height: 58px !important;
  padding: 12px 14px;
  border-radius: 8px;
  box-shadow: 0 0 0 1px var(--border-color) inset;
}

.composer-action {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
}

.stop-action {
  --el-button-bg-color: #c2410c;
  --el-button-border-color: #c2410c;
  --el-button-hover-bg-color: #9a3412;
  --el-button-hover-border-color: #9a3412;
}
</style>

