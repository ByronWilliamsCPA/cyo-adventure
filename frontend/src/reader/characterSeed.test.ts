import { describe, expect, it, vi } from 'vitest'

import { makeFetchActiveCharacterBinding } from './characterSeed'

import type { AxiosInstance } from 'axios'
import type { CharacterListView, CharacterView } from '../client/types.gen'

function character(overrides: Partial<CharacterView>): CharacterView {
  return {
    id: 'char-1',
    profile_id: 'p1',
    name: 'Astra',
    archetype: 'scout',
    look: 'avatar_01',
    is_active: true,
    books_completed: 0,
    attributes: {},
    seed_var_state: {},
    created_at: '2026-08-01T00:00:00Z',
    retired_at: null,
    ...overrides,
  }
}

function apiReturning(characters: CharacterView[]): {
  api: AxiosInstance
  get: ReturnType<typeof vi.fn>
} {
  const body: CharacterListView = { characters }
  const get = vi.fn(() => Promise.resolve({ data: body }))
  return { api: { get } as unknown as AxiosInstance, get }
}

describe('makeFetchActiveCharacterBinding (ADR-028 Task 9, I1)', () => {
  it("reads the server's seed_var_state and never re-derives one from attributes", async () => {
    // The discriminator: `attributes` and `seed_var_state` are deliberately
    // DIFFERENT here. Today the backend mapping (characters/seeding.py::
    // character_seed) is the identity, so a client that re-derived the seed
    // from `attributes` would look correct against a realistic fixture and
    // only diverge the day that mapping stops being the identity. Giving the
    // two fields different values makes the two implementations observably
    // different right now: this test passes only for the one that CONSUMES
    // the server's field.
    const { api } = apiReturning([
      character({
        attributes: { might: 2, wits: 1, nerve: 0 },
        seed_var_state: { might: 40, wits: 41, nerve: 42 },
      }),
    ])
    const binding = await makeFetchActiveCharacterBinding(api)('p1')
    expect(binding).toEqual({
      characterName: 'Astra',
      seed: { might: 40, wits: 41, nerve: 42 },
    })
  })

  it('requests the profile it was asked about', async () => {
    const { api, get } = apiReturning([character({})])
    await makeFetchActiveCharacterBinding(api)('p_other')
    expect(get).toHaveBeenCalledWith('/v1/characters', { params: { profile_id: 'p_other' } })
  })

  it('picks the active character by is_active, not by list position', async () => {
    // characterApi.ts documents the list as active-first but explicitly tells
    // callers not to rely on order; this pins that we do not.
    const { api } = apiReturning([
      character({
        id: 'char-retired',
        name: 'Old',
        is_active: false,
        seed_var_state: { might: 9 },
      }),
      character({ id: 'char-live', name: 'New', is_active: true, seed_var_state: { might: 1 } }),
    ])
    const binding = await makeFetchActiveCharacterBinding(api)('p1')
    expect(binding).toEqual({ characterName: 'New', seed: { might: 1 } })
  })

  it('resolves null when the profile has no active character', async () => {
    const { api } = apiReturning([character({ is_active: false })])
    expect(await makeFetchActiveCharacterBinding(api)('p1')).toBeNull()
  })

  it('resolves null (never rejects) when the lookup fails', async () => {
    // A child must never be kept out of a book by a character lookup: every
    // failure mode degrades to "open unseeded", which is the pre-Task-9
    // behavior. ReaderPage turns a null into NO_CHARACTER_BINDING.
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const api = {
      get: vi.fn(() => Promise.reject(new Error('offline'))),
    } as unknown as AxiosInstance
    expect(await makeFetchActiveCharacterBinding(api)('p1')).toBeNull()
  })

  it('resolves null when the body is not a character list', async () => {
    const api = {
      get: vi.fn(() => Promise.resolve({ data: { characters: 'nope' } })),
    } as unknown as AxiosInstance
    expect(await makeFetchActiveCharacterBinding(api)('p1')).toBeNull()
  })

  it('degrades to seed: undefined when a stale cached payload omits seed_var_state (N2)', async () => {
    // seed_var_state is required by the generated CharacterView type, so
    // nothing in this file can express "missing" through the type system.
    // The frontend service worker's catch-all /v1/* rule is NetworkFirst
    // with a 5s timeout over a 7-day cache (vite.config.ts), so a body
    // cached before this field shipped can still be served during a
    // deployment window. Deleting the key after construction models exactly
    // that runtime shape, bypassing the compile-time guarantee on purpose.
    const stale = character({}) as Record<string, unknown>
    delete stale.seed_var_state
    const { api } = apiReturning([stale as unknown as CharacterView])
    const binding = await makeFetchActiveCharacterBinding(api)('p1')
    expect(binding).toEqual({ characterName: 'Astra', seed: undefined })
  })
})
