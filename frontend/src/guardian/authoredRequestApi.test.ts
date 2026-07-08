import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeAuthoredRequestApi } from './authoredRequestApi'

function fakeAxios(data: unknown) {
  const get = vi.fn().mockResolvedValue({ data })
  const post = vi.fn().mockResolvedValue({ data })
  return { api: { get, post } as unknown as AxiosInstance, get, post }
}

describe('makeAuthoredRequestApi', () => {
  it('createAuthored posts the body to the authored endpoint and returns the created view', async () => {
    const created = { id: 'req-1', status: 'approved', concept_id: 'concept-1' }
    const body = {
      request_text: 'A story about a brave fox',
      age_band: '8-11' as const,
      length: 'medium' as const,
      narrative_style: 'prose' as const,
    }
    const { api, post } = fakeAxios(created)
    const result = await makeAuthoredRequestApi(api).createAuthored(body)
    expect(post).toHaveBeenCalledWith('/v1/story-requests/authored', body)
    expect(result).toEqual(created)
  })

  it('listProfiles returns the profiles array', async () => {
    const profiles = [
      {
        id: 'p1',
        display_name: 'Rae',
        age_band: '8-11',
        reading_level_cap: 99,
        avatar: null,
        tts_enabled: false,
        created_at: '2026-07-04T10:00:00Z',
      },
    ]
    const { api, get } = fakeAxios({ profiles })
    const result = await makeAuthoredRequestApi(api).listProfiles()
    expect(get).toHaveBeenCalledWith('/v1/profiles')
    expect(result).toEqual(profiles)
  })

  it('listFamilies returns the families array', async () => {
    const families = [{ id: 'fam-1', name: 'The Ambers' }]
    const { api, get } = fakeAxios({ families })
    const result = await makeAuthoredRequestApi(api).listFamilies()
    expect(get).toHaveBeenCalledWith('/v1/admin/families')
    expect(result).toEqual(families)
  })
})
