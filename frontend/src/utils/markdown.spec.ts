import { renderMarkdown } from './markdown'

describe('renderMarkdown', () => {
  it('renders tables and escapes raw HTML', () => {
    const html = renderMarkdown('| name | value |\n|---|---|\n| A | 1 |\n<script>alert(1)</script>')

    expect(html).toContain('<table>')
    expect(html).toContain('&lt;script&gt;')
    expect(html).not.toContain('<script>')
  })
})

