import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeConnectionsApi, type FamilyConnectionMineItem } from './connectionsApi'

function fakeAxios(overrides: {
  get?: unknown
  post?: unknown
  delete?: unknown
}) {
  const get = vi.fn().mockResolvedValue({ data: overrides.get })
  const post = vi.fn().mockResolvedValue({ data: overrides.post })
  const del = vi.fn().mockResolvedValue({ data: overrides.delete })
  return { api: { get, post, delete: del } as unknown as AxiosInstance, get, post, del }
}

const ITEM: FamilyConnectionMineItem = {
  id: 'conn-1',
  direction: 'viewer',
  counterpart_family_id: 'fam-2',
  counterpart_family_name: 'Smith Family',
  my_consent: false,
  active: false,
  created_at: '2026-07-16T12:00:00Z',
}

describe('makeConnectionsApi listMine', () => {
  it('gets the caller family connection list', async () => {
    const { api, get } = fakeAxios({ get: { connections: [ITEM] } })
    const result = await makeConnectionsApi(api).listMine()
    expect(get).toHaveBeenCalledWith('/v1/family-connections/mine')
    expect(result).toEqual([ITEM])
  })

  it('degrades a malformed body to an empty array', async () => {
    const { api } = fakeAxios({ get: {} })
    const result = await makeConnectionsApi(api).listMine()
    expect(result).toEqual([])
  })
})

describe('makeConnectionsApi consent', () => {
  it('posts to the consent endpoint for the given connection id', async () => {
    const consented = { ...ITEM, my_consent: true }
    const { api, post } = fakeAxios({ post: consented })
    const result = await makeConnectionsApi(api).consent('conn-1')
    expect(post).toHaveBeenCalledWith('/v1/family-connections/conn-1/consent')
    expect(result).toEqual(consented)
  })
})

describe('makeConnectionsApi revoke', () => {
  it('deletes the consent endpoint for the given connection id', async () => {
    const revoked = { ...ITEM, my_consent: false, active: false }
    const { api, del } = fakeAxios({ delete: revoked })
    const result = await makeConnectionsApi(api).revoke('conn-1')
    expect(del).toHaveBeenCalledWith('/v1/family-connections/conn-1/consent')
    expect(result).toEqual(revoked)
  })
})
