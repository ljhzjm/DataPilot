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
})
