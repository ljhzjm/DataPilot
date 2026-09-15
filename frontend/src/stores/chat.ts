import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  abortMessage,
  archiveConversation as archiveConversationRequest,
  createConversation,
  deleteConversation as deleteConversationRequest,
  getConversation,
  listConversations,
  streamMessage,
} from '../api/chat'
import type {
  AgentStep,
  ChatMessage,
  ConversationSummary,
} from '../types/chat'

function nowIso(): string {
  return new Date().toISOString()
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<ConversationSummary[]>([])
  const conversationTotal = ref(0)
  const conversationQuery = ref('')
  const includeArchived = ref(false)
  const conversationLoading = ref(false)
  const pageSize = 20
  const currentConversationId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const error = ref<string | null>(null)
  let abortController: AbortController | null = null
  let activeAssistantId: string | null = null

  const currentSteps = computed<AgentStep[]>(() => {
    const assistantMessages = messages.value.filter((message) => message.role === 'assistant')
    const latestMessage = assistantMessages[assistantMessages.length - 1]
    return latestMessage?.steps ?? []
  })

  const totalTokens = computed(() =>
    currentSteps.value.reduce(
      (total, step) => total + step.usage.input_tokens + step.usage.output_tokens,
      0,
    ),
  )

  async function initialize(): Promise<void> {
    error.value = null
    try {
      await loadConversations()
      if (conversations.value.length) {
        await selectConversation(conversations.value[0].id)
      } else {
        await createNewConversation()
      }
    } catch (cause) {
      error.value = toErrorMessage(cause)
    }
  }

  async function loadConversations(reset = true): Promise<void> {
    conversationLoading.value = true
    try {
      const page = await listConversations({
        limit: pageSize,
        offset: reset ? 0 : conversations.value.length,
        query: conversationQuery.value.trim() || undefined,
        includeArchived: includeArchived.value,
      })
      conversations.value = reset
        ? page.items
        : [...conversations.value, ...page.items]
      conversationTotal.value = page.total
    } finally {
      conversationLoading.value = false
    }
  }

  async function loadMoreConversations(): Promise<void> {
    if (conversations.value.length >= conversationTotal.value) {
      return
    }
    await loadConversations(false)
  }

  async function searchConversations(query: string): Promise<void> {
    conversationQuery.value = query
    await loadConversations(true)
  }

  async function setIncludeArchived(value: boolean): Promise<void> {
    includeArchived.value = value
    await loadConversations(true)
  }

  async function createNewConversation(): Promise<void> {
    const conversation = await createConversation()
    currentConversationId.value = conversation.id
    messages.value = conversation.messages
    await loadConversations()
  }

  async function selectConversation(conversationId: string): Promise<void> {
    if (isStreaming.value) {
      stopStreaming()
    }
    const conversation = await getConversation(conversationId)
    currentConversationId.value = conversation.id
    messages.value = conversation.messages
  }

  async function sendMessage(content: string): Promise<void> {
    const question = content.trim()
    if (!question || isStreaming.value) {
      return
    }
    if (!currentConversationId.value) {
      await createNewConversation()
    }

    const conversationId = currentConversationId.value
    if (!conversationId) {
      return
    }

    error.value = null
    isStreaming.value = true
    abortController = new AbortController()

    const localUserMessage: ChatMessage = {
      id: `local-user-${Date.now()}`,
      role: 'user',
      content: question,
      status: 'completed',
      tool_calls: [],
      steps: [],
      created_at: nowIso(),
    }
    const assistantDraft: ChatMessage = {
      id: `local-assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      status: 'streaming',
      tool_calls: [],
      steps: [],
      created_at: nowIso(),
    }
    messages.value.push(localUserMessage, assistantDraft)
    const assistantMessage = messages.value[messages.value.length - 1]
    if (!assistantMessage) {
      isStreaming.value = false
      abortController = null
      return
    }
    activeAssistantId = assistantMessage.id
    const clientRequestId = crypto.randomUUID()
    let lastEventId: string | undefined

    try {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          await streamMessage(
            conversationId,
            question,
            {
              clientRequestId,
              lastEventId,
            },
            (event) => {
              lastEventId = event.id || lastEventId
          if (event.event === 'start') {
            const assistantId = String(event.data.assistant_message_id ?? '')
            if (assistantId) {
              assistantMessage.id = assistantId
              activeAssistantId = assistantId
            }
          } else if (event.event === 'step') {
            const step = event.data.step as AgentStep | undefined
            if (step) {
              assistantMessage.steps.push(step)
            }
          } else if (event.event === 'text') {
            assistantMessage.content = `${assistantMessage.content ?? ''}${String(
              event.data.text ?? '',
            )}`
          } else if (event.event === 'text_reset') {
            assistantMessage.content = ''
          } else if (event.event === 'done') {
            assistantMessage.status = 'completed'
          } else if (event.event === 'aborted') {
            assistantMessage.status = 'aborted'
          } else if (event.event === 'error') {
            assistantMessage.status = 'error'
            error.value = String(event.data.message ?? '执行失败')
          }
            },
            abortController.signal,
          )
          break
        } catch (cause) {
          if (
            cause instanceof DOMException &&
            cause.name === 'AbortError'
          ) {
            throw cause
          }
          if (attempt >= 2) {
            throw cause
          }
          await new Promise((resolve) => window.setTimeout(resolve, 500 * 2 ** attempt))
        }
      }
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') {
        assistantMessage.status = 'aborted'
      } else {
        assistantMessage.status = 'error'
        error.value = toErrorMessage(cause)
      }
    } finally {
      isStreaming.value = false
      abortController = null
      activeAssistantId = null
      await loadConversations().catch(() => undefined)
    }
  }

  async function stopStreaming(): Promise<void> {
    if (currentConversationId.value && activeAssistantId) {
      await abortMessage(
        currentConversationId.value,
        activeAssistantId,
      ).catch(() => undefined)
    }
    abortController?.abort()
    isStreaming.value = false
  }

  function clearError(): void {
    error.value = null
  }

  async function archiveConversation(
    conversationId: string,
    archived: boolean,
  ): Promise<void> {
    await archiveConversationRequest(conversationId, archived)
    await loadConversations(true)
    if (
      archived
      && !includeArchived.value
      && currentConversationId.value === conversationId
    ) {
      if (conversations.value.length) {
        await selectConversation(conversations.value[0].id)
      } else {
        await createNewConversation()
      }
    }
  }

  async function removeConversation(conversationId: string): Promise<void> {
    await deleteConversationRequest(conversationId)
    if (currentConversationId.value === conversationId) {
      currentConversationId.value = null
      messages.value = []
    }
    await loadConversations(true)
    if (!currentConversationId.value) {
      if (conversations.value.length) {
        await selectConversation(conversations.value[0].id)
      } else {
        await createNewConversation()
      }
    }
  }

  return {
    conversations,
    conversationTotal,
    conversationQuery,
    includeArchived,
    conversationLoading,
    currentConversationId,
    messages,
    currentSteps,
    totalTokens,
    isStreaming,
    error,
    initialize,
    loadMoreConversations,
    searchConversations,
    setIncludeArchived,
    createNewConversation,
    selectConversation,
    sendMessage,
    stopStreaming,
    archiveConversation,
    removeConversation,
    clearError,
  }
})

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
