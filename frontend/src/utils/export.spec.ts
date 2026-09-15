import { describe, expect, it } from 'vitest'

import type { ChatMessage } from '../types/chat'
import {
  createConversationMarkdown,
  createCsv,
  safeExportName,
} from './export'

describe('export utilities', () => {
  it('creates RFC 4180 compatible CSV', () => {
    const csv = createCsv(
      [
        { region: 'East', note: 'a,b', total: 120 },
        { region: 'West', note: 'line\nbreak', total: 80 },
      ],
      ['region', 'note', 'total'],
    )

    expect(csv).toBe(
      'region,note,total\r\nEast,"a,b",120\r\nWest,"line\nbreak",80',
    )
  })

  it('exports conversation steps as Markdown', () => {
    const messages: ChatMessage[] = [
      {
        id: 'assistant-1',
        role: 'assistant',
        content: '分析完成',
        status: 'completed',
        tool_calls: [],
        created_at: '2026-09-15T10:00:00Z',
        steps: [
          {
            step: 1,
            assistant_content: '执行聚合查询。',
            tool_calls: [],
            usage: { input_tokens: 10, output_tokens: 4 },
            tool_executions: [
              {
                tool_call_id: 'call-1',
                tool_name: 'run_sql',
                arguments: { sql: 'SELECT 1' },
                result: { rows: [{ value: 1 }] },
                error: null,
                duration_ms: 2,
              },
            ],
          },
        ],
      },
    ]

    const markdown = createConversationMarkdown('销售分析', messages)

    expect(markdown).toContain('# 销售分析')
    expect(markdown).toContain('### 步骤 1')
    expect(markdown).toContain('#### 工具：run_sql')
    expect(markdown).toContain('"sql": "SELECT 1"')
    expect(markdown).toContain('分析完成')
  })

  it('sanitizes filenames', () => {
    expect(safeExportName(' 销售:分析/2026? ', 'fallback')).toBe(
      '销售-分析-2026',
    )
    expect(safeExportName('...', 'fallback')).toBe('fallback')
  })
})
