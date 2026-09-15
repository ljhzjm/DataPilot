<!--
Vue 概念：页面组件负责组合子组件并调用 Pinia action；`onMounted`
在页面首次显示时加载会话列表，布局本身只负责左对话、右轨迹。
-->
<script setup lang="ts">
import { onMounted } from 'vue'

import ChatPanel from '../components/ChatPanel.vue'
import TraceTimeline from '../components/TraceTimeline.vue'
import { useChatStore } from '../stores/chat'

const store = useChatStore()

onMounted(() => {
  void store.initialize()
})
</script>

<template>
  <main class="app-shell">
    <header class="app-header">
      <div class="brand">
        <span class="brand-mark">DP</span>
        <h1>DataPilot</h1>
      </div>
      <span class="environment-label">Conversational Analytics</span>
    </header>

    <div class="workspace-grid">
      <ChatPanel />
      <TraceTimeline
        :steps="store.currentSteps"
        :streaming="store.isStreaming"
        :error="store.error"
      />
    </div>
  </main>
</template>
