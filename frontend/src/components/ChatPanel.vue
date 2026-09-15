<!--
Vue 概念：组件通过 Pinia store 共享状态，模板中的事件处理函数负责调用 action。
此处把“会话选择、消息列表、输入框”组成左栏，页面本身不直接请求接口。
-->
<script setup lang="ts">
import { Database, History, Plus } from '@lucide/vue'
import { ref } from 'vue'

import { useChatStore } from '../stores/chat'
import DatasetDrawer from './DatasetDrawer.vue'
import MessageComposer from './MessageComposer.vue'
import MessageList from './MessageList.vue'

const store = useChatStore()
const historyOpen = ref(false)
const datasetOpen = ref(false)

async function chooseConversation(conversationId: string): Promise<void> {
  historyOpen.value = false
  await store.selectConversation(conversationId)
}

async function createConversation(): Promise<void> {
  historyOpen.value = false
  await store.createNewConversation()
}
</script>

<template>
  <section class="chat-panel">
    <header class="panel-header">
      <div>
        <span class="panel-kicker">会话</span>
        <strong>数据分析对话</strong>
      </div>
      <div class="panel-actions">
        <el-tooltip content="数据表" placement="bottom">
          <el-button
            :icon="Database"
            circle
            aria-label="数据表"
            @click="datasetOpen = true"
          />
        </el-tooltip>
        <el-tooltip content="历史会话" placement="bottom">
          <el-button
            :icon="History"
            circle
            aria-label="历史会话"
            @click="historyOpen = true"
          />
        </el-tooltip>
        <el-tooltip content="新建会话" placement="bottom">
          <el-button
            type="primary"
            :icon="Plus"
            circle
            aria-label="新建会话"
            @click="createConversation"
          />
        </el-tooltip>
      </div>
    </header>

    <el-alert
      v-if="store.error"
      class="chat-error"
      type="error"
      :title="store.error"
      closable
      @close="store.clearError"
    />

    <MessageList
      :messages="store.messages"
      :streaming="store.isStreaming"
      @suggest="store.sendMessage"
    />
    <MessageComposer
      :streaming="store.isStreaming"
      @send="store.sendMessage"
      @stop="store.stopStreaming"
    />

    <el-drawer v-model="historyOpen" title="历史会话" size="320px">
      <button
        v-for="conversation in store.conversations"
        :key="conversation.id"
        type="button"
        class="history-item"
        :class="{ active: conversation.id === store.currentConversationId }"
        @click="chooseConversation(conversation.id)"
      >
        <strong>{{ conversation.title }}</strong>
        <span>{{ conversation.message_count }} 条消息</span>
      </button>
    </el-drawer>
    <DatasetDrawer v-model="datasetOpen" />
  </section>
</template>

<style scoped>
.chat-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface-color);
}

.panel-header {
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 18px;
  border-bottom: 1px solid var(--border-color);
  background: var(--surface-color);
}

.panel-header > div:first-child {
  display: grid;
  gap: 2px;
}

.panel-kicker {
  color: var(--muted-color);
  font-size: 11px;
  text-transform: uppercase;
}

.panel-actions {
  display: flex;
  gap: 8px;
}

.chat-error {
  margin: 12px 18px 0;
  width: auto;
}

.history-item {
  width: 100%;
  display: grid;
  gap: 4px;
  padding: 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.history-item:hover,
.history-item.active {
  border-color: var(--border-color);
  background: var(--canvas-color);
}

.history-item strong {
  color: var(--text-color);
  font-size: 14px;
}

.history-item span {
  color: var(--muted-color);
  font-size: 12px;
}
</style>
