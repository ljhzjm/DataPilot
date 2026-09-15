export type MessageRole = 'system' | 'user' | 'assistant' | 'tool'
export type MessageStatus = 'streaming' | 'completed' | 'aborted' | 'error'

export interface TokenUsage {
  input_tokens: number
  output_tokens: number
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface ToolExecution {
  tool_call_id: string
  tool_name: string
  arguments: Record<string, unknown>
  result: unknown
  error: string | null
  duration_ms: number
}

export interface AgentStep {
  step: number
  assistant_content: string | null
  tool_calls: ToolCall[]
  tool_executions: ToolExecution[]
  usage: TokenUsage
}

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string | null
  status: MessageStatus
  tool_calls: ToolCall[]
  steps: AgentStep[]
  created_at: string
}

export interface ConversationSummary {
  id: string
  title: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface ConversationDetail {
  id: string
  title: string
  messages: ChatMessage[]
  created_at: string
  updated_at: string
}

export interface ChartSpec {
  type: 'line' | 'bar' | 'area' | 'pie' | 'scatter'
  title: string
  x_field: string
  y_fields: string[]
  data: Record<string, unknown>[]
}

export interface ChartArtifact {
  kind: 'chart'
  spec: ChartSpec
}

export interface StreamEvent {
  id?: string
  event: 'start' | 'step' | 'text' | 'text_reset' | 'done' | 'error' | 'aborted'
  data: Record<string, unknown>
}
