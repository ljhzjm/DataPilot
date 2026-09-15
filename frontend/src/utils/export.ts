import type { ChatMessage } from '../types/chat'

export function createCsv(
  rows: Record<string, unknown>[],
  columns: string[],
): string {
  const header = columns.map(csvCell).join(',')
  const body = rows.map((row) =>
    columns.map((column) => csvCell(row[column])).join(','),
  )
  return [header, ...body].join('\r\n')
}

export function createConversationMarkdown(
  title: string,
  messages: ChatMessage[],
): string {
  const lines = [
    `# ${title}`,
    '',
    `> 导出时间：${new Date().toISOString()}`,
    '',
  ]

  messages.forEach((message, index) => {
    const role = message.role === 'user' ? '用户' : 'DataPilot'
    lines.push(`## ${index + 1}. ${role}`, '')
    if (message.content) {
      lines.push(message.content, '')
    }
    message.steps.forEach((step) => {
      lines.push(`### 步骤 ${step.step}`, '')
      if (step.assistant_content) {
        lines.push(`模型摘要：${step.assistant_content}`, '')
      }
      step.tool_executions.forEach((execution) => {
        lines.push(`#### 工具：${execution.tool_name}`, '')
        lines.push('参数：', '', '```json')
        lines.push(formatValue(execution.arguments))
        lines.push('```', '')
        if (execution.error) {
          lines.push('错误：', '', '```text')
          lines.push(execution.error)
          lines.push('```', '')
        } else {
          lines.push('结果：', '', '```json')
          lines.push(formatValue(execution.result))
          lines.push('```', '')
        }
      })
    })
  })
  return lines.join('\n').trimEnd() + '\n'
}

export function safeExportName(
  value: string,
  fallback = 'datapilot-export',
): string {
  const withoutControlCharacters = [...value.trim()]
    .map((character) => (character.charCodeAt(0) < 32 ? '-' : character))
    .join('')
  const safe = withoutControlCharacters
    .replace(/[<>:"/\\|?*]/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[.-]+|[.-]+$/g, '')
    .slice(0, 80)
  return safe || fallback
}

export function exportTimestamp(date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    '-',
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join('')
}

export function downloadTextFile(
  content: string,
  filename: string,
  mimeType = 'text/plain;charset=utf-8',
): void {
  downloadBlob(
    new Blob([content], { type: mimeType }),
    filename,
  )
}

export function downloadDataUrl(dataUrl: string, filename: string): void {
  const link = document.createElement('a')
  link.href = dataUrl
  link.download = filename
  link.style.display = 'none'
  document.body.append(link)
  link.click()
  link.remove()
}

function csvCell(value: unknown): string {
  const raw =
    value === null || value === undefined
      ? ''
      : typeof value === 'object'
        ? JSON.stringify(value)
        : String(value)
  if (/[",\r\n]/.test(raw)) {
    return `"${raw.replace(/"/g, '""')}"`
  }
  return raw
}

function formatValue(value: unknown): string {
  const formatted =
    typeof value === 'string'
      ? value
      : (JSON.stringify(value, null, 2) ?? String(value))
  return formatted.length > 4000
    ? `${formatted.slice(0, 4000)}\n...[truncated]`
    : formatted
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
