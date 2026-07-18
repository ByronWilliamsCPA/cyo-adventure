import { describe, expect, it, vi } from 'vitest'

import { makeProfilesApi, type ProfileCreateBody } from './profilesApi'

function fakeAxios() {
  return {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  }
}

describe('makeProfilesApi', () => {
  it('lists profiles from GET /v1/profiles', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({ data: { profiles: [{ id: 'p1' }] } })
    const result = await makeProfilesApi(api as never).list()
    expect(api.get).toHaveBeenCalledWith('/v1/profiles')
    expect(result).toEqual([{ id: 'p1' }])
  })

  it('creates via POST /v1/profiles and returns the view', async () => {
    const api = fakeAxios()
    api.post.mockResolvedValue({ data: { id: 'p2', display_name: 'Nova' } })
    const body: ProfileCreateBody = { display_name: 'Nova', age_band: '5-8' }
    const result = await makeProfilesApi(api as never).create(body)
    expect(api.post).toHaveBeenCalledWith('/v1/profiles', body)
    expect(result.id).toBe('p2')
  })

  it('updates via PATCH /v1/profiles/:id', async () => {
    const api = fakeAxios()
    api.patch.mockResolvedValue({ data: { id: 'p1', avatar: null } })
    const result = await makeProfilesApi(api as never).update('p1', { avatar: null })
    expect(api.patch).toHaveBeenCalledWith('/v1/profiles/p1', { avatar: null })
    expect(result.avatar).toBeNull()
  })

  // ADR-015 G3: the wire shape only, per ProfileEnvelopeFields' header
  // comment -- these two fields are not yet accepted by the live backend,
  // this just pins that the adapter passes them through verbatim when a
  // caller (ProfileFormDialog) includes them.
  it('passes request_auto_approve/monthly_request_envelope through on create', async () => {
    const api = fakeAxios()
    api.post.mockResolvedValue({ data: { id: 'p3' } })
    const body: ProfileCreateBody = {
      display_name: 'Nova',
      age_band: '5-8',
      request_auto_approve: true,
      monthly_request_envelope: 3,
    }
    await makeProfilesApi(api as never).create(body)
    expect(api.post).toHaveBeenCalledWith('/v1/profiles', body)
  })

  it('passes request_auto_approve/monthly_request_envelope through on update', async () => {
    const api = fakeAxios()
    api.patch.mockResolvedValue({ data: { id: 'p1' } })
    await makeProfilesApi(api as never).update('p1', {
      request_auto_approve: false,
      monthly_request_envelope: null,
    })
    expect(api.patch).toHaveBeenCalledWith('/v1/profiles/p1', {
      request_auto_approve: false,
      monthly_request_envelope: null,
    })
  })
})
