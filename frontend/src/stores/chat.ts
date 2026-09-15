import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  createConversation,
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
  const currentConversationId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const error = ref<string | null>(null)
  let abortController: AbortController | null = null

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
      conversations.value = await listConversations()
      if (conversations.value.length) {
        await selectConversation(conversations.value[0].id)
      } else {
        await createNewConversation()
      }
    } catch (cause) {
      error.value = toErrorMessage(cause)
    }
  }

  async function loadConversations(): Promise<void> {
    conversations.value = await listConversations()
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
    const assistantMessage: ChatMessage = {
      id: `local-assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      status: 'streaming',
      tool_calls: [],
      steps: [],
      created_at: nowIso(),
    }
    messages.value.push(localUserMessage, assistantMessage)

    try {
      await streamMessage(
        conversationId,
        question,
        (event) => {
          if (event.event === 'start') {
            const assistantId = String(event.data.assistant_message_id ?? '')
            if (assistantId) {
              assistantMessage.id = assistantId
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
      await loadConversations().catch(() => undefined)
    }
  }

  function stopStreaming(): void {
    abortController?.abort()
    isStreaming.value = false
  }

  function clearError(): void {
    error.value = null
  }

  return {
    conversations,
    currentConversationId,
    messages,
    currentSteps,
    totalTokens,
    isStreaming,
    error,
    initialize,
    createNewConversation,
    selectConversation,
    sendMessage,
    stopStreaming,
    clearError,
  }
})

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
