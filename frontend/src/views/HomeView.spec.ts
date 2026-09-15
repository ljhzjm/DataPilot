import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { vi } from 'vitest'

import HomeView from './HomeView.vue'

describe('HomeView', () => {
  it('renders the application shell', () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('skip network in unit test')))
    const wrapper = mount(HomeView, {
      global: {
        plugins: [createPinia(), ElementPlus],
      },
    })

    expect(wrapper.text()).toContain('DataPilot')
    expect(wrapper.text()).toContain('执行轨迹')
  })
})
