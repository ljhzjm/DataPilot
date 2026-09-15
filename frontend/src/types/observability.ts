export interface UsageSummary {
  call_count: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  estimated_cost_usd: number
  average_latency_ms: number
  error_count: number
}

export interface UsageRecord {
  id: string
  trace_id: string | null
  task: string
  provider: string
  model: string
  input_tokens: number
  output_tokens: number
  estimated_cost_usd: number
  latency_ms: number
  success: boolean
  error_type: string | null
  created_at: string
}

export interface UsagePage {
  items: UsageRecord[]
  total: number
  limit: number
  offset: number
}

