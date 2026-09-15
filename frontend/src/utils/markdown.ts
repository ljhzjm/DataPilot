import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
  typographer: false,
})

export function renderMarkdown(content: string | null): string {
  return markdown.render(content || '')
}

