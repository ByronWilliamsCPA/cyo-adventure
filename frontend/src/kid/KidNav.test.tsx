import { render, screen, waitFor } from '@testing-library/react'
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

  it('discards a stale profile fetch that resolves after the profileId has already switched', async () => {
    let resolveP1: ((value: { data: { profiles: typeof PROFILES } }) => void) | undefined
    const p1Promise = new Promise<{ data: { profiles: typeof PROFILES } }>((resolve) => {
      resolveP1 = resolve
    })
    const p2Profile = {
      id: 'p2',
      display_name: 'Theo',
      age_band: '5-8',
      reading_level_cap: 99,
      avatar: 'owl',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    }
    // First call (for p1) hangs; second call (for p2, after the rerender)
    // resolves right away.
    mockGet.mockReturnValueOnce(p1Promise)
    mockGet.mockResolvedValueOnce({ data: { profiles: [p2Profile] } })

    const { rerender } = render(
      <MemoryRouter>
        <KidNav profileId="p1" />
      </MemoryRouter>
    )

    rerender(
      <MemoryRouter>
        <KidNav profileId="p2" />
      </MemoryRouter>
    )

    expect(await screen.findByText('Theo')).toBeInTheDocument()

    // The stale p1 lookup finally resolves; it must not clobber the already
    // displayed p2 identity (the keyed `loaded.forId === profileId` guard).
    resolveP1?.({ data: { profiles: PROFILES } })
    await waitFor(() => expect(screen.getByText('Theo')).toBeInTheDocument())
    expect(screen.queryByText('Mia')).not.toBeInTheDocument()
  })

  it('shows the generic label, not the previous profile name, when the new profileId fetch fails', async () => {
    mockGet.mockResolvedValueOnce({ data: { profiles: PROFILES } })
    mockGet.mockRejectedValueOnce(new Error('offline'))

    const { rerender } = render(
      <MemoryRouter>
        <KidNav profileId="p1" />
      </MemoryRouter>
    )
    expect(await screen.findByText('Mia')).toBeInTheDocument()

    rerender(
      <MemoryRouter>
        <KidNav profileId="p2" />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByText('My books')).toBeInTheDocument())
    expect(screen.queryByText('Mia')).not.toBeInTheDocument()
  })
})
