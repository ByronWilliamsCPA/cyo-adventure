import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeDeviceDownloadsApi } from './deviceDownloadsApi'

describe('makeDeviceDownloadsApi.list', () => {
  it('GETs /v1/device-downloads and resolves the response body', async () => {
    const items = [
      {
        id: 'row-1',
        device_id: 'device-1',
        profile_id: 'p1',
        profile_name: 'Maya',
        storybook_id: 's1',
        storybook_title: 'The Lighthouse Mystery',
        downloaded_at: '2026-08-01T00:00:00Z',
        last_confirmed_at: '2026-08-09T00:00:00Z',
      },
    ]
    const get = vi.fn(() => Promise.resolve({ data: items }))
    const api = makeDeviceDownloadsApi({ get } as unknown as AxiosInstance)
    await expect(api.list()).resolves.toEqual(items)
    expect(get).toHaveBeenCalledWith('/v1/device-downloads')
  })
})
