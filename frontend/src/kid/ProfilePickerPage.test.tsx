import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ProfilePickerPage } from './ProfilePickerPage'

const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

function renderPicker() {
  return render(
    <MemoryRouter>
      <ProfilePickerPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset()
})

describe('ProfilePickerPage', () => {
  it('renders a tile per profile linking to that library', async () => {
    mockGet.mockResolvedValue({
      data: {
        profiles: [
          {
            id: 'p1',
            display_name: 'Reader A',
            age_band: '10-13',
            reading_level_cap: 99,
            avatar: 'fox',
            tts_enabled: false,
            created_at: '2026-07-02T00:00:00Z',
          },
          {
            id: 'p2',
            display_name: 'Nova',
            age_band: '5-8',
            reading_level_cap: 99,
            avatar: null,
            tts_enabled: false,
            created_at: '2026-07-02T00:00:00Z',
          },
        ],
      },
    })
    renderPicker()
    const tile = await screen.findByRole('link', { name: /Reader A/ })
    expect(tile).toHaveAttribute('href', '/library/p1')
    // Avatar-less profile falls back to the initial letter.
    expect(screen.getByText('N')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Add Child/i })).toHaveAttribute(
      'href',
      '/guardian/profiles'
    )
  })

  it('shows the empty state when no profiles exist', async () => {
    mockGet.mockResolvedValue({ data: { profiles: [] } })
    renderPicker()
    expect(await screen.findByText(/No profiles yet/i)).toBeInTheDocument()
  })

  it('shows an error state when the list fails', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    renderPicker()
    expect(await screen.findByText(/Oops, we hit a snag/i)).toBeInTheDocument()
  })

  it('announces the error state via a role=alert live region', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    renderPicker()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Oops, we hit a snag/i)
  })

  it('recovers to the ready state when Try again succeeds after a failed load', async () => {
    const user = userEvent.setup()
    mockGet.mockRejectedValueOnce(new Error('boom'))
    mockGet.mockResolvedValueOnce({
      data: {
        profiles: [
          {
            id: 'p1',
            display_name: 'Reader A',
            age_band: '10-13',
            reading_level_cap: 99,
            avatar: 'fox',
            tts_enabled: false,
            created_at: '2026-07-02T00:00:00Z',
          },
        ],
      },
    })
    renderPicker()

    await screen.findByText(/Oops, we hit a snag/i)
    await user.click(screen.getByRole('button', { name: /try again/i }))

    expect(await screen.findByRole('link', { name: /Reader A/ })).toHaveAttribute(
      'href',
      '/library/p1'
    )
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('offers a grown-up sign-in link from the error state', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    renderPicker()

    await screen.findByText(/Oops, we hit a snag/i)
    expect(screen.getByRole('link', { name: /I am a grown-up/i })).toHaveAttribute(
      'href',
      '/guardian/login'
    )
  })
})
