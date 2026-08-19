import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeProviderAllowlistApi } from './providerAllowlistApi'

function fakeAxios(data: unknown) {
  const get = vi.fn().mockResolvedValue({ data })
  const post = vi.fn().mockResolvedValue({ data })
  const put = vi.fn().mockResolvedValue({ data })
  const del = vi.fn().mockResolvedValue({ data })
  return {
    api: { get, post, put, delete: del } as unknown as AxiosInstance,
    get,
    post,
    put,
    del,
  }
}

describe('makeProviderAllowlistApi', () => {
  it('list fetches the allowlist rows', async () => {
    const rows = [
      {
        id: 'a1',
        provider: 'anthropic',
        model_id: 'claude-sonnet-4-6',
        enabled: true,
        display_name: null,
      },
    ]
    const { api, get } = fakeAxios({ rows })
    const result = await makeProviderAllowlistApi(api).list()
    expect(get).toHaveBeenCalledWith('/v1/admin/provider-allowlist')
    expect(result.rows).toEqual(rows)
  })

  it('create posts the new entry', async () => {
    const created = {
      id: 'a1',
      provider: 'modal',
      model_id: 'google/gemma-4-26b-a4b-it',
      enabled: true,
      display_name: 'Modal endpoint default',
    }
    const { api, post } = fakeAxios(created)
    const result = await makeProviderAllowlistApi(api).create({
      provider: 'modal',
      model_id: 'google/gemma-4-26b-a4b-it',
      display_name: 'Modal endpoint default',
    })
    expect(post).toHaveBeenCalledWith('/v1/admin/provider-allowlist', {
      provider: 'modal',
      model_id: 'google/gemma-4-26b-a4b-it',
      display_name: 'Modal endpoint default',
    })
    expect(result).toEqual(created)
  })

  it('update puts the enabled/display_name change', async () => {
    const updated = {
      id: 'a1',
      provider: 'modal',
      model_id: 'google/gemma-4-26b-a4b-it',
      enabled: false,
      display_name: 'Modal endpoint default',
    }
    const { api, put } = fakeAxios(updated)
    const result = await makeProviderAllowlistApi(api).update('a1', {
      enabled: false,
      display_name: 'Modal endpoint default',
    })
    expect(put).toHaveBeenCalledWith('/v1/admin/provider-allowlist/a1', {
      enabled: false,
      display_name: 'Modal endpoint default',
    })
    expect(result).toEqual(updated)
  })

  it('remove deletes and returns the refreshed list', async () => {
    const { api, del } = fakeAxios({ rows: [] })
    const result = await makeProviderAllowlistApi(api).remove('a1')
    expect(del).toHaveBeenCalledWith('/v1/admin/provider-allowlist/a1')
    expect(result.rows).toEqual([])
  })
})
