import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

import { useActiveCharacter } from './useActiveCharacter'

import type { CharacterView } from '../client/types.gen'

beforeEach(() => {
  mockGet.mockReset()
})

const LUNA: CharacterView = {
  id: 'char-1',
  profile_id: 'p1',
  name: 'Luna',
  archetype: 'scout',
  look: 'avatar_01',
  is_active: true,
  books_completed: 0,
  attributes: {},
  created_at: '2026-08-01T00:00:00Z',
  retired_at: null,
}

describe('useActiveCharacter', () => {
  it('resolves to none for a well-formed empty character list', async () => {
    mockGet.mockResolvedValue({ data: { characters: [] } })
    const { result } = renderHook(() => useActiveCharacter('p1'))

    await waitFor(() => expect(result.current.state.status).toBe('none'))
  })

  it('resolves to ready with the active character when the list has one', async () => {
    mockGet.mockResolvedValue({ data: { characters: [LUNA] } })
    const { result } = renderHook(() => useActiveCharacter('p1'))

    await waitFor(() => expect(result.current.state.status).toBe('ready'))
    expect(result.current.state).toEqual({ status: 'ready', character: LUNA })
  })

  it('resolves to error on a rejected request', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    const { result } = renderHook(() => useActiveCharacter('p1'))

    await waitFor(() => expect(result.current.state.status).toBe('error'))
  })

  // The central discriminating case: this is what makes 'none' and 'error'
  // impossible to confuse. A merely-unparsed response (a real character the
  // client failed to understand) must never read as "this profile has no
  // character," since KidShell's first-run gate treats 'none' as "safe to
  // show the creator" and would let a child create a second character while
  // masking a real one.
  it("an unparseable response never resolves to 'none'", async () => {
    mockGet.mockResolvedValue({ data: {} }) // missing `characters` entirely
    const { result } = renderHook(() => useActiveCharacter('p1'))

    await waitFor(() => expect(result.current.state.status).toBe('error'))
    expect(result.current.state.status).not.toBe('none')
  })

  it("a wrong-shaped characters field (not an array) resolves to 'error', not 'none'", async () => {
    mockGet.mockResolvedValue({ data: { characters: 'not-an-array' } })
    const { result } = renderHook(() => useActiveCharacter('p1'))

    await waitFor(() => expect(result.current.state.status).toBe('error'))
    expect(result.current.state.status).not.toBe('none')
  })

  it('resolves to unauthenticated on a 401', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 401 } })
    const { result } = renderHook(() => useActiveCharacter('p1'))

    await waitFor(() => expect(result.current.state.status).toBe('unauthenticated'))
  })

  it('resolves to forbidden on a 403', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    const { result } = renderHook(() => useActiveCharacter('p1'))

    await waitFor(() => expect(result.current.state.status).toBe('forbidden'))
  })
})
