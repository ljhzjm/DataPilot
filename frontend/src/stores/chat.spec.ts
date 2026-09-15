import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type StreamHandler = (event: {
  id?: string
  event: 'text' | 'done'
  data: Record<string, unknown>
}) => void

let releaseStream: (() => void) | undefined

vi.mock('../api/chat', () => ({
  listConversations: vi.fn().mockResolvedValue([]),
  createConversation: vi.fn().mockResolvedValue({
    id: 'conversation-1',
    title: '新会话',
    messages: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }),
  getConversation: vi.fn(),
  abortMessage: vi.fn().mockResolvedValue(undefined),
  streamMessage: vi.fn(
    async (
      _conversationId: string,
      _content: string,
      _options: object,
      onEvent: StreamHandler,
    ) => {
      onEvent({
        id: '1-0',
        event: 'text',
        data: { text: '逐字内容' },
      })
      await new Promise<void>((resolve) => {
        releaseStream = resolve
      })
      onEvent({
        id: '2-0',
        event: 'done',
        data: { status: 'completed' },
      })
    },
  ),
}))

import { useChatStore } from './chat'

describe('chat store streaming', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    releaseStream = undefined
    vi.stubGlobal('crypto', {
      randomUUID: () => 'request-1',
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('updates the reactive assistant message before the stream completes', async () => {
    const store = useChatStore()
    const pending = store.sendMessage('测试流式更新')

    await vi.waitFor(() => {
      expect(store.messages[1]?.content).toBe('逐字内容')
    })
    expect(store.isStreaming).toBe(true)

    releaseStream?.()
    await pending

    expect(store.messages[1]?.status).toBe('completed')
    expect(store.isStreaming).toBe(false)
  })
})

