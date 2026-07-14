import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeDeviceGrantApi } from './deviceGrantApi'

function fakeAxios(overrides: Partial<AxiosInstance>): AxiosInstance {
  return overrides as AxiosInstance
}

describe('makeDeviceGrantApi', () => {
  it('mints a device grant with no label when omitted', async () => {
    const post = vi.fn().mockResolvedValue({
      data: {
        id: 'grant-1',
        token: 'tok-1',
        expires_at: '2026-07-11T12:00:00Z',
        family_id: 'fam-1',
      },
    })
    const api = makeDeviceGrantApi(fakeAxios({ post }))

    const result = await api.mint()

    expect(post).toHaveBeenCalledWith('/v1/device-grants', undefined)
    expect(result).toEqual({
      id: 'grant-1',
      token: 'tok-1',
      expires_at: '2026-07-11T12:00:00Z',
      family_id: 'fam-1',
    })
  })

  it('mints a device grant with a label when provided', async () => {
    const post = vi.fn().mockResolvedValue({
      data: {
        id: 'grant-1',
        token: 'tok-1',
        expires_at: '2026-07-11T12:00:00Z',
        family_id: 'fam-1',
      },
    })
    const api = makeDeviceGrantApi(fakeAxios({ post }))

    await api.mint('Kitchen tablet')

    expect(post).toHaveBeenCalledWith('/v1/device-grants', { label: 'Kitchen tablet' })
  })

  it('propagates a mint rejection unchanged', async () => {
    const error = new Error('mint failed')
    const post = vi.fn().mockRejectedValue(error)
    const api = makeDeviceGrantApi(fakeAxios({ post }))

    await expect(api.mint()).rejects.toBe(error)
  })

  it('lists device grants (never the token)', async () => {
    const get = vi.fn().mockResolvedValue({
      data: [{ id: 'grant-1', label: 'Kitchen tablet', created_at: '2026-07-11T00:00:00Z', revoked_at: null }],
    })
    const api = makeDeviceGrantApi(fakeAxios({ get }))

    const result = await api.list()

    expect(get).toHaveBeenCalledWith('/v1/device-grants')
    expect(result).toEqual([
      { id: 'grant-1', label: 'Kitchen tablet', created_at: '2026-07-11T00:00:00Z', revoked_at: null },
    ])
  })

  it('revokes a device grant by id', async () => {
    const del = vi.fn().mockResolvedValue({ data: undefined })
    const api = makeDeviceGrantApi(fakeAxios({ delete: del }))

    await api.revoke('grant-1')

    expect(del).toHaveBeenCalledWith('/v1/device-grants/grant-1')
  })

  it('propagates a revoke rejection unchanged', async () => {
    const error = new Error('revoke failed')
    const del = vi.fn().mockRejectedValue(error)
    const api = makeDeviceGrantApi(fakeAxios({ delete: del }))

    await expect(api.revoke('grant-1')).rejects.toBe(error)
  })
})
