import type {
  ConversationDetail,
  ConversationSummary,
  StreamEvent,
} from '../types/chat'

interface ApiErrorBody {
  detail?: string
}

async function apiRequest<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(body.detail || `请求失败：${response.status}`)
  }
  return (await response.json()) as T
}

export function listConversations(): Promise<ConversationSummary[]> {
  return apiRequest<ConversationSummary[]>('/api/conversations')
}

export function createConversation(): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>('/api/conversations', {
    method: 'POST',
  })
}

export function getConversation(conversationId: string): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>(`/api/conversations/${conversationId}`)
}

export async function streamMessage(
  conversationId: string,
  content: string,
  options: {
    clientRequestId: string
    lastEventId?: string
  },
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  if (options.lastEventId) {
    headers['Last-Event-ID'] = options.lastEventId
  }
  const response = await fetch(`/api/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      content,
      client_request_id: options.clientRequestId,
    }),
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error(`流式请求失败：${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    buffer = consumeFrames(buffer, onEvent)
    if (done) {
      break
    }
  }
}

function consumeFrames(
  input: string,
  onEvent: (event: StreamEvent) => void,
): string {
  let buffer = input
  for (;;) {
    const separator = buffer.match(/\r?\n\r?\n/)
    if (!separator || separator.index === undefined) {
      return buffer
    }

    const frame = buffer.slice(0, separator.index)
    buffer = buffer.slice(separator.index + separator[0].length)
    const event = parseFrame(frame)
    if (event) {
      onEvent(event)
    }
  }
}

function parseFrame(frame: string): StreamEvent | null {
  let eventId: string | undefined
  let eventName = 'message'
  const dataLines: string[] = []

  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('id:')) {
      eventId = line.slice(3).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }

  if (!dataLines.length) {
    return null
  }

  const data = JSON.parse(dataLines.join('\n')) as Record<string, unknown>
  return {
    id: eventId,
    event: eventName as StreamEvent['event'],
    data,
  }
}

export async function abortMessage(
  conversationId: string,
  messageId: string,
): Promise<void> {
  await fetch(
    `/api/conversations/${conversationId}/messages/${messageId}/abort`,
    {
      method: 'POST',
    },
  )
}
