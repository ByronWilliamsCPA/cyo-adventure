import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'

import { CharacterPicker } from './CharacterPicker'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
})

const LUNA = {
  id: 'char-1',
  profile_id: 'p1',
  name: 'Luna',
  archetype: 'scout',
  look: 'avatar_01',
  is_active: true,
  books_completed: 3,
  attributes: { courage: 4 },
  created_at: '2026-08-01T00:00:00Z',
  retired_at: null,
}

const REX = {
  id: 'char-2',
  profile_id: 'p1',
  name: 'Rex',
  archetype: 'guardian',
  look: 'avatar_02',
  is_active: false,
  books_completed: 1,
  attributes: { courage: 1 },
  created_at: '2026-08-02T00:00:00Z',
  retired_at: null,
}

describe('CharacterPicker', () => {
  it('shows the active character as selected', async () => {
    mockGet.mockResolvedValue({ data: { characters: [LUNA, REX] } })
    render(<CharacterPicker profileId="p1" />)

    // Toggle buttons, not ARIA radios: the tiles have no roving tabindex or
    // arrow-key handling, so `aria-pressed` is the honest contract. A
    // regression to role="radio"/aria-checked would fail these queries.
    const lunaTile = await screen.findByRole('button', { name: /Luna/ })
    const rexTile = screen.getByRole('button', { name: /Rex/ })
    expect(lunaTile).toHaveAttribute('aria-pressed', 'true')
    expect(rexTile).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByRole('radiogroup')).toBeNull()
    expect(screen.queryByRole('radio')).toBeNull()
    // The tiles are a plain list, which is what the tab-per-tile behavior
    // actually is.
    expect(within(screen.getByRole('list')).getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('Currently reading as')).toBeInTheDocument()
    // The chosen look's swatch is shown on each tile (avatar-led, mirroring
    // ProfilePickerPage's AvatarCircle), not just during creation.
    expect(within(lunaTile).getByText('🔴')).toBeInTheDocument()
    expect(within(rexTile).getByText('🟠')).toBeInTheDocument()
  })

  it('choosing a different character calls activate and updates selection without a page reload', async () => {
    mockGet.mockResolvedValue({ data: { characters: [LUNA, REX] } })
    mockPost.mockResolvedValue({ data: { ...REX, is_active: true } })
    const onActiveCharacterChange = vi.fn()
    const user = userEvent.setup()
    render(<CharacterPicker profileId="p1" onActiveCharacterChange={onActiveCharacterChange} />)

    const rexTile = await screen.findByRole('button', { name: /Rex/ })
    await user.click(rexTile)

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/v1/characters/char-2/activate')

    // Same render tree, no navigation, no unmount: query the same elements
    // again and see the flip reflected in place.
    const lunaTileAfter = screen.getByRole('button', { name: /Luna/ })
    const rexTileAfter = screen.getByRole('button', { name: /Rex/ })
    expect(rexTileAfter).toHaveAttribute('aria-pressed', 'true')
    expect(lunaTileAfter).toHaveAttribute('aria-pressed', 'false')
    expect(onActiveCharacterChange).toHaveBeenCalledWith({ ...REX, is_active: true })
  })

  it('a profile with no characters shows the creator, not an empty picker', async () => {
    mockGet.mockResolvedValue({ data: { characters: [] } })
    render(<CharacterPicker profileId="p1" />)

    await screen.findByRole('heading', { name: /Make your character/i })
    expect(screen.queryByRole('list', { name: /Choose your character/i })).toBeNull()
  })
})

/**
 * The permission, failure, and retry arms. These are the paths a child on a
 * flaky home connection or an expired grown-up session actually hits, and
 * none of them can be reached from the happy-path tests above: each needs
 * the list fetch (or the activate POST) to fail in a specific way.
 */
describe('CharacterPicker error and permission states', () => {
  let errorSpy: MockInstance

  beforeEach(() => {
    // logApiError writes to console.error on every one of these paths; the
    // assertions below are about the rendered surface, not the log line.
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    errorSpy.mockRestore()
  })

  it('sends a child to find a grown-up when the session has expired (401)', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 401 } })
    render(<CharacterPicker profileId="p1" />)

    expect(await screen.findByText('Time to find your grown-up')).toBeInTheDocument()
    // Not the generic failure state: a 401 is not something a child can
    // retry their way out of, so no "Try again" is offered.
    expect(screen.queryByRole('button', { name: /Try again/i })).toBeNull()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('sends a child to find a grown-up when the profile is not theirs (403)', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    render(<CharacterPicker profileId="p1" />)

    expect(await screen.findByText('Time to find your grown-up')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Try again/i })).toBeNull()
  })

  it('offers Try again on a failed load, and Try again re-issues the GET', async () => {
    mockGet.mockRejectedValueOnce(new Error('network down'))
    const user = userEvent.setup()
    render(<CharacterPicker profileId="p1" />)

    expect(await screen.findByText('We lost your character')).toBeInTheDocument()
    const listCalls = () => mockGet.mock.calls.filter((call) => call[0] === '/v1/characters')
    expect(listCalls()).toHaveLength(1)

    // The retry has to actually refetch, not just re-render the error: the
    // second GET is the whole point of the reload key.
    mockGet.mockResolvedValue({ data: { characters: [LUNA, REX] } })
    await user.click(screen.getByRole('button', { name: /Try again/i }))

    expect(await screen.findByRole('button', { name: /Luna/ })).toBeInTheDocument()
    expect(listCalls()).toHaveLength(2)
    expect(listCalls()[1]).toEqual(['/v1/characters', { params: { profile_id: 'p1' } }])
    expect(screen.queryByText('We lost your character')).toBeNull()
  })

  it('disables every tile while an activation is in flight, so a second tap cannot start a concurrent activate', async () => {
    const TARA = {
      id: 'char-3',
      profile_id: 'p1',
      name: 'Tara',
      archetype: 'scholar',
      look: 'avatar_03',
      is_active: false,
      books_completed: 0,
      attributes: {},
      created_at: '2026-08-03T00:00:00Z',
      retired_at: null,
    }
    mockGet.mockResolvedValue({ data: { characters: [LUNA, REX, TARA] } })
    // Holds Rex's activate() request open so its response is fully under
    // this test's control, mirroring the exact race the fix closes: a
    // second tile is tapped while the first activation is still in flight.
    let resolveActivate: ((value: { data: typeof REX }) => void) | undefined
    mockPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveActivate = resolve
        })
    )
    const user = userEvent.setup()
    render(<CharacterPicker profileId="p1" />)

    const rexTile = await screen.findByRole('button', { name: /Rex/ })
    const taraTile = screen.getByRole('button', { name: /Tara/ })
    await user.click(rexTile)

    // Rex's request is still pending: every tile, not just Rex's own, must
    // be disabled so a second tap cannot start a concurrent activate() call.
    expect(rexTile).toBeDisabled()
    expect(taraTile).toBeDisabled()
    await user.click(taraTile)
    expect(mockPost).toHaveBeenCalledTimes(1)

    resolveActivate?.({ data: { ...REX, is_active: true } })
    await waitFor(() => expect(rexTile).toHaveAttribute('aria-pressed', 'true'))

    // Tara's blocked tap never reached the API: only Rex's own request was
    // ever sent, and it is the one that won.
    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/v1/characters/char-2/activate')
    expect(taraTile).toBeEnabled()
  })

  it('shows a retry message and re-enables the tile when activate fails', async () => {
    mockGet.mockResolvedValue({ data: { characters: [LUNA, REX] } })
    mockPost.mockRejectedValue(new Error('activate boom'))
    const onActiveCharacterChange = vi.fn()
    const user = userEvent.setup()
    render(<CharacterPicker profileId="p1" onActiveCharacterChange={onActiveCharacterChange} />)

    const rexTile = await screen.findByRole('button', { name: /Rex/ })
    await user.click(rexTile)

    expect(await screen.findByRole('alert')).toHaveTextContent("That didn't work. Let's try again.")
    // The `.finally` cleared activatingId, so the tile is tappable again
    // rather than stuck disabled/aria-busy on a failure the child can retry.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Rex/ })).toBeEnabled()
    })
    expect(screen.getByRole('button', { name: /Rex/ })).not.toHaveAttribute('aria-busy')
    // The failed activation changed nothing: Luna is still the active one
    // and no parent was told otherwise.
    expect(screen.getByRole('button', { name: /Luna/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /Rex/ })).toHaveAttribute('aria-pressed', 'false')
    expect(onActiveCharacterChange).not.toHaveBeenCalled()
  })
})
