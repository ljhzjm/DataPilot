import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import ToolResultView from './ToolResultView.vue'
import DataGrid from './DataGrid.vue'

describe('ToolResultView', () => {
  it('renders query rows as a data grid', () => {
    const wrapper = mount(ToolResultView, {
      props: {
        result: {
          columns: ['region', 'total'],
          rows: [
            { region: 'East', total: 120 },
            { region: 'West', total: 80 },
          ],
        },
        expanded: false,
      },
      global: {
        plugins: [ElementPlus],
      },
    })

    const grid = wrapper.findComponent(DataGrid)
    expect(grid.exists()).toBe(true)
    expect(grid.props('rows')).toEqual([
      { region: 'East', total: 120 },
      { region: 'West', total: 80 },
    ])
  })

  it('renders unknown results as text without executing code', () => {
    const wrapper = mount(ToolResultView, {
      props: {
        result: { message: 'completed' },
        expanded: false,
      },
      global: {
        plugins: [ElementPlus],
      },
    })

    expect(wrapper.find('pre').text()).toContain('"completed"')
  })

  it('renders Python outputs and artifact download links', () => {
    const wrapper = mount(ToolResultView, {
      props: {
        result: {
          ok: true,
          stdout: 'saved result\n',
          stderr: '',
          artifacts: [
            {
              id: 'artifact-1',
              filename: 'result.csv',
              mime_type: 'text/csv',
              size: 2048,
              url: '/api/artifacts/artifact-1',
              created_at: '2026-09-15T10:00:00Z',
            },
            {
              id: 'artifact-2',
              filename: 'chart.png',
              mime_type: 'image/png',
              size: 4096,
              url: '/api/artifacts/artifact-2',
              created_at: '2026-09-15T10:00:00Z',
            },
          ],
        },
        expanded: false,
      },
      global: {
        plugins: [ElementPlus],
      },
    })

    expect(wrapper.text()).toContain('saved result')
    expect(wrapper.find('a[download="result.csv"]').attributes('href')).toBe(
      '/api/artifacts/artifact-1',
    )
    expect(wrapper.find('img').attributes('src')).toBe('/api/artifacts/artifact-2')
  })
})
