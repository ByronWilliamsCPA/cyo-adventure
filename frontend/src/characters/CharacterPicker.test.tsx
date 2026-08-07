import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

    const lunaTile = await screen.findByRole('radio', { name: /Luna/ })
    const rexTile = screen.getByRole('radio', { name: /Rex/ })
    expect(lunaTile).toHaveAttribute('aria-checked', 'true')
    expect(rexTile).toHaveAttribute('aria-checked', 'false')
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

    const rexTile = await screen.findByRole('radio', { name: /Rex/ })
    await user.click(rexTile)

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/v1/characters/char-2/activate')

    // Same render tree, no navigation, no unmount: query the same elements
    // again and see the flip reflected in place.
    const lunaTileAfter = screen.getByRole('radio', { name: /Luna/ })
    const rexTileAfter = screen.getByRole('radio', { name: /Rex/ })
    expect(rexTileAfter).toHaveAttribute('aria-checked', 'true')
    expect(lunaTileAfter).toHaveAttribute('aria-checked', 'false')
    expect(onActiveCharacterChange).toHaveBeenCalledWith({ ...REX, is_active: true })
  })

  it('a profile with no characters shows the creator, not an empty picker', async () => {
    mockGet.mockResolvedValue({ data: { characters: [] } })
    render(<CharacterPicker profileId="p1" />)

    await screen.findByRole('heading', { name: /Make your character/i })
    expect(screen.queryByRole('radiogroup', { name: /Choose your character/i })).toBeNull()
  })
})
