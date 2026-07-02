import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ProfilesPage } from './ProfilesPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()
const fakeApi = { get: mockGet, post: mockPost, patch: mockPatch }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const readerA = {
  id: 'p1',
  display_name: 'Reader A',
  age_band: '10-13',
  reading_level_cap: 99,
  avatar: 'fox',
  tts_enabled: false,
  created_at: '2026-07-02T00:00:00Z',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ProfilesPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ data: { profiles: [readerA] } })
  mockPost.mockReset()
  mockPatch.mockReset()
})

describe('ProfilesPage', () => {
  it('lists profiles with their caps', async () => {
    renderPage()
    expect(await screen.findByText('Reader A')).toBeInTheDocument()
    expect(screen.getByText(/Ages 10-13/)).toBeInTheDocument()
  })

  it('creates a profile through the dialog', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({
      data: { ...readerA, id: 'p2', display_name: 'Nova', age_band: '5-8', avatar: null },
    })
    renderPage()
    await user.click(await screen.findByRole('button', { name: /Add child/i }))
    await user.type(screen.getByLabelText(/Name/i), 'Nova')
    await user.selectOptions(screen.getByLabelText(/Age band/i), '5-8')
    await user.click(screen.getByRole('button', { name: /Save/i }))
    expect(mockPost).toHaveBeenCalledWith(
      '/v1/profiles',
      expect.objectContaining({ display_name: 'Nova', age_band: '5-8' })
    )
    expect(await screen.findByText('Nova')).toBeInTheDocument()
  })

  it('edits caps through the dialog', async () => {
    const user = userEvent.setup()
    mockPatch.mockResolvedValue({
      data: { ...readerA, reading_level_cap: 4.5 },
    })
    renderPage()
    await user.click(await screen.findByRole('button', { name: /Edit Reader A/i }))
    const cap = screen.getByLabelText(/Reading level cap/i)
    await user.clear(cap)
    await user.type(cap, '4.5')
    await user.click(screen.getByRole('button', { name: /Save/i }))
    expect(mockPatch).toHaveBeenCalledWith(
      '/v1/profiles/p1',
      expect.objectContaining({ reading_level_cap: 4.5 })
    )
  })

  it('surfaces a create failure without closing silently', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue(new Error('boom'))
    renderPage()
    await user.click(await screen.findByRole('button', { name: /Add child/i }))
    await user.type(screen.getByLabelText(/Name/i), 'Nova')
    await user.click(screen.getByRole('button', { name: /Save/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save/i)
  })
})
