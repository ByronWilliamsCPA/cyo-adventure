import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KidNav } from './KidNav'

const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

function renderNav(profileId = 'p1') {
  return render(
    <MemoryRouter>
      <KidNav profileId={profileId} />
    </MemoryRouter>
  )
}

const PROFILES = [
  {
    id: 'p1',
    display_name: 'Mia',
    age_band: '5-8',
    reading_level_cap: 99,
    avatar: 'fox',
    tts_enabled: false,
    created_at: '2026-07-02T00:00:00Z',
  },
]

beforeEach(() => {
  mockGet.mockReset()
})

describe('KidNav', () => {
  it('always offers a Switch reader link to the profile picker', async () => {
    mockGet.mockResolvedValue({ data: { profiles: PROFILES } })
    renderNav()
    const link = await screen.findByRole('link', { name: /switch reader/i })
    expect(link).toHaveAttribute('href', '/kids')
  })

  it('shows whose books these are once the profile loads', async () => {
    mockGet.mockResolvedValue({ data: { profiles: PROFILES } })
    renderNav('p1')
    expect(await screen.findByText('Mia')).toBeInTheDocument()
  })

  it('still renders the Switch reader link when the profile lookup fails', async () => {
    mockGet.mockRejectedValue(new Error('offline'))
    renderNav()
    // The control needs no data, so a failed lookup must not remove it.
    expect(await screen.findByRole('link', { name: /switch reader/i })).toHaveAttribute(
      'href',
      '/kids'
    )
  })
})
