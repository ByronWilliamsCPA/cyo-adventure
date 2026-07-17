import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeAdminLibraryApi } from './adminLibraryApi'

function fakeAxios(data: unknown) {
  const get = vi.fn().mockResolvedValue({ data })
  const api = { get } as unknown as AxiosInstance
  return { api, get }
}

const ITEM = {
  storybook_id: 's1',
  title: 'The Lantern',
  status: 'published',
  version: 2,
  age_band: '6-8',
  family_id: 'fam-1',
  current_published_version: 2,
  created_at: '2026-06-01T00:00:00Z',
  updated_at: '2026-06-10T00:00:00Z',
}

describe('makeAdminLibraryApi', () => {
  it('lists all storybooks with no status filter', async () => {
    const { api, get } = fakeAxios({ items: [ITEM] })
    const result = await makeAdminLibraryApi(api).list()
    expect(get).toHaveBeenCalledWith('/v1/admin/storybooks', { params: undefined })
    expect(result).toHaveLength(1)
    expect(result[0].storybook_id).toBe('s1')
  })

  it('passes the status filter as a query param', async () => {
    const { api, get } = fakeAxios({ items: [] })
    await makeAdminLibraryApi(api).list('archived')
    expect(get).toHaveBeenCalledWith('/v1/admin/storybooks', {
      params: { status: 'archived' },
    })
  })
})
