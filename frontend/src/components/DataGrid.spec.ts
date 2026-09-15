import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DataGrid from './DataGrid.vue'

describe('DataGrid export', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('downloads the visible rows as CSV', async () => {
    let capturedBlob: Blob | null = null
    const createObjectUrl = vi.fn((blob: Blob) => {
      capturedBlob = blob
      return 'blob:result'
    })
    const revokeObjectUrl = vi.fn()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: createObjectUrl,
      revokeObjectURL: revokeObjectUrl,
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const wrapper = mount(DataGrid, {
      props: {
        columns: ['region', 'total'],
        rows: [{ region: 'East', total: 120 }],
      },
      global: {
        plugins: [ElementPlus],
      },
    })

    await wrapper.get('button[aria-label="导出 CSV"]').trigger('click')

    expect(createObjectUrl).toHaveBeenCalledTimes(1)
    expect(capturedBlob).not.toBeNull()
    expect((capturedBlob as Blob | null)?.type).toBe('text/csv;charset=utf-8')
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:result')
  })
})
