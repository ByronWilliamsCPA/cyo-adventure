import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { ARCHETYPE_ROSTER, makeCharactersApi } from './characterApi'

import type { CharacterView } from '../client/types.gen'

function fakeAxios(overrides: Partial<AxiosInstance>): AxiosInstance {
  return overrides as AxiosInstance
}

const LUNA: CharacterView = {
  id: 'char-1',
  profile_id: 'p1',
  name: 'Luna',
  archetype: 'scout',
  look: 'avatar_01',
  is_active: true,
  books_completed: 0,
  attributes: {},
  seed_var_state: {},
  created_at: '2026-08-01T00:00:00Z',
  retired_at: null,
}

describe('ARCHETYPE_ROSTER', () => {
  // #VERIFY citation: characterApi.ts's ARCHETYPE_ROSTER docstring. This is a
  // literal array, not a derived comparison, so a reordering of the roster
  // fails this test rather than moving silently with it: the order is the
  // backend's stored numeric code (ARCHETYPE_CODES), not this file's to choose.
  it('pins the six-item roster order to the backend wire format', () => {
    expect(ARCHETYPE_ROSTER).toEqual([
      'scout',
      'guardian',
      'trickster',
      'scholar',
      'healer',
      'wildheart',
    ])
  })
})

describe('makeCharactersApi', () => {
  it('list() issues a GET to /v1/characters with profile_id and returns the characters array', async () => {
    const get = vi.fn().mockResolvedValue({ data: { characters: [LUNA] } })
    const api = makeCharactersApi(fakeAxios({ get }))

    const result = await api.list('p1')

    expect(get).toHaveBeenCalledWith('/v1/characters', { params: { profile_id: 'p1' } })
    expect(result).toEqual([LUNA])
  })

  it('create() issues a POST to /v1/characters with the create body and returns the character', async () => {
    const post = vi.fn().mockResolvedValue({ data: LUNA })
    const api = makeCharactersApi(fakeAxios({ post }))
    const body = { profile_id: 'p1', name: 'Luna', archetype: 'scout', look: 'avatar_01' }

    const result = await api.create(body)

    expect(post).toHaveBeenCalledWith('/v1/characters', body)
    expect(result).toEqual(LUNA)
  })

  it('update() issues a PATCH to /v1/characters/{id} with the update body and returns the character', async () => {
    const updated = { ...LUNA, name: 'Luna Jane' }
    const patch = vi.fn().mockResolvedValue({ data: updated })
    const api = makeCharactersApi(fakeAxios({ patch }))

    const result = await api.update('char-1', { name: 'Luna Jane' })

    expect(patch).toHaveBeenCalledWith('/v1/characters/char-1', { name: 'Luna Jane' })
    expect(result).toEqual(updated)
  })

  it('activate() issues a POST to /v1/characters/{id}/activate with no body and returns the character', async () => {
    const activated = { ...LUNA, is_active: true }
    const post = vi.fn().mockResolvedValue({ data: activated })
    const api = makeCharactersApi(fakeAxios({ post }))

    const result = await api.activate('char-1')

    expect(post).toHaveBeenCalledWith('/v1/characters/char-1/activate')
    expect(result).toEqual(activated)
  })

  it('retire() issues a POST to /v1/characters/{id}/retire with no body and returns the character', async () => {
    const retired = { ...LUNA, is_active: false, retired_at: '2026-08-07T00:00:00Z' }
    const post = vi.fn().mockResolvedValue({ data: retired })
    const api = makeCharactersApi(fakeAxios({ post }))

    const result = await api.retire('char-1')

    expect(post).toHaveBeenCalledWith('/v1/characters/char-1/retire')
    expect(result).toEqual(retired)
  })

  it('remove() issues a DELETE to /v1/characters/{id} and resolves to undefined', async () => {
    const del = vi.fn().mockResolvedValue({ data: undefined })
    const api = makeCharactersApi(fakeAxios({ delete: del }))

    const result = await api.remove('char-1')

    expect(del).toHaveBeenCalledWith('/v1/characters/char-1')
    expect(result).toBeUndefined()
  })
})
