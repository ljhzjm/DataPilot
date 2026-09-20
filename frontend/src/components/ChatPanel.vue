<!--
Vue 概念：组件通过 Pinia store 共享状态，模板中的事件处理函数负责调用 action。
此处把“会话选择、消息列表、输入框”组成左栏，页面本身不直接请求接口。
-->
<script setup lang="ts">
import {
  Archive,
  ArchiveRestore,
  Database,
  Download,
  History,
  LogOut,
  Plus,
  Gauge,
  Trash2,
} from '@lucide/vue'
import 'element-plus/es/components/message-box/style/css'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { computed, defineAsyncComponent, ref } from 'vue'

import { useChatStore } from '../stores/chat'
import { useAuthStore } from '../stores/auth'
import {
  createConversationMarkdown,
  downloadTextFile,
  exportTimestamp,
  safeExportName,
} from '../utils/export'
import MessageComposer from './MessageComposer.vue'
import MessageList from './MessageList.vue'

const store = useChatStore()
const auth = useAuthStore()
const DatasetDrawer = defineAsyncComponent(() => import('./DatasetDrawer.vue'))
const ObservabilityDrawer = defineAsyncComponent(
  () => import('./ObservabilityDrawer.vue'),
)
const historyOpen = ref(false)
const datasetOpen = ref(false)
const observabilityOpen = ref(false)
const currentTitle = computed(
  () =>
    store.conversations.find(
      (conversation) => conversation.id === store.currentConversationId,
    )?.title || 'DataPilot 会话',
)

async function chooseConversation(conversationId: string): Promise<void> {
  historyOpen.value = false
  await store.selectConversation(conversationId)
}

async function createConversation(): Promise<void> {
  historyOpen.value = false
  await store.createNewConversation()
}

async function toggleArchive(conversationId: string, archived: boolean): Promise<void> {
  await store.archiveConversation(conversationId, archived)
}

async function deleteConversation(conversationId: string): Promise<void> {
  await ElMessageBox.confirm('删除后无法恢复，是否继续？', '删除会话', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  await store.removeConversation(conversationId)
}

function exportConversation(): void {
  const markdown = createConversationMarkdown(currentTitle.value, store.messages)
  downloadTextFile(
    markdown,
    `${safeExportName(currentTitle.value, 'datapilot-conversation')}-${exportTimestamp()}.md`,
    'text/markdown;charset=utf-8',
  )
}

async function logout(): Promise<void> {
  await auth.logout()
  window.location.assign('/login')
}
</script>

<template>
  <section class="chat-panel">
    <header class="panel-header">
      <div>
        <span class="panel-kicker">{{ auth.workspace?.name || '会话' }}</span>
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
        <el-tooltip content="模型用量" placement="bottom">
          <el-button
            :icon="Gauge"
            circle
            aria-label="模型用量"
            @click="observabilityOpen = true"
          />
        </el-tooltip>
        <el-tooltip content="导出会话" placement="bottom">
          <el-button
            :icon="Download"
            circle
            :disabled="!store.messages.length || store.isStreaming"
            aria-label="导出会话"
            @click="exportConversation"
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
        <el-tooltip content="退出登录" placement="bottom">
          <el-button
            :icon="LogOut"
            circle
            aria-label="退出登录"
            @click="logout"
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
      <div class="history-tools">
        <el-input
          clearable
          placeholder="搜索会话"
          @input="store.searchConversations"
          @clear="store.searchConversations('')"
        />
        <el-checkbox
          :model-value="store.includeArchived"
          @change="store.setIncludeArchived(Boolean($event))"
        >
          显示归档
        </el-checkbox>
      </div>

      <div v-loading="store.conversationLoading" class="history-list">
        <article
          v-for="conversation in store.conversations"
          :key="conversation.id"
          class="history-item"
          :class="{ active: conversation.id === store.currentConversationId }"
        >
          <button
            type="button"
            class="history-main"
            @click="chooseConversation(conversation.id)"
          >
            <strong>{{ conversation.title }}</strong>
            <span>
              {{ conversation.message_count }} 条消息
              <template v-if="conversation.archived_at"> · 已归档</template>
            </span>
          </button>
          <div class="history-actions">
            <el-tooltip
              :content="conversation.archived_at ? '恢复会话' : '归档会话'"
              placement="left"
            >
              <el-button
                text
                :icon="conversation.archived_at ? ArchiveRestore : Archive"
                @click="toggleArchive(conversation.id, !conversation.archived_at)"
              />
            </el-tooltip>
            <el-tooltip content="删除会话" placement="left">
              <el-button
                text
                :icon="Trash2"
                @click="deleteConversation(conversation.id)"
              />
            </el-tooltip>
          </div>
        </article>
      </div>

      <el-button
        v-if="store.conversations.length < store.conversationTotal"
        class="history-more"
        text
        @click="store.loadMoreConversations"
      >
        加载更多
      </el-button>
    </el-drawer>
    <DatasetDrawer v-model="datasetOpen" />
    <ObservabilityDrawer v-model="observabilityOpen" />
  </section>
</template>

<style scoped>
.chat-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  padding: 6px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
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

.history-tools {
  display: grid;
  gap: 10px;
  margin-bottom: 14px;
}

.history-list {
  min-height: 100px;
}

.history-main {
  min-width: 0;
  display: grid;
  gap: 4px;
  padding: 6px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.history-actions {
  display: flex;
  align-items: center;
}

.history-more {
  width: 100%;
  margin-top: 12px;
}

@media (max-width: 720px) {
  .panel-header {
    flex-wrap: wrap;
    gap: 8px;
    padding: 8px 10px;
  }

  .panel-header > div:first-child {
    flex: 1 1 auto;
    min-width: 0;
  }

  .panel-header strong {
    overflow: hidden;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .panel-kicker {
    display: none;
  }

  .panel-actions {
    order: 2;
    flex-basis: 100%;
    flex-shrink: 0;
    justify-content: flex-end;
    gap: 1px;
  }

  .panel-actions :deep(.el-button) {
    width: 28px;
    height: 28px;
    margin-left: 0;
  }
}
</style>
