import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KidNav } from './KidNav'
import { _resetKidProfileFetch } from './useKidProfile'

// W3.2/W3.4: KidNav now also fetches GET /v1/me/progress (ring, badge case);
// route by URL so the existing profile-lookup test setups (which configure
// responses with mockResolvedValueOnce/mockReturnValueOnce, unaware of a
// second endpoint) keep working unmodified, and progress-specific tests can
// drive `progressGet` independently.
const profilesGet = vi.fn<(...args: unknown[]) => Promise<unknown>>()
const progressGet = vi.fn<(...args: unknown[]) => Promise<unknown>>()
const mockGet = vi.fn((url: string): Promise<unknown> => {
  if (url === '/v1/me/progress') return progressGet()
  return profilesGet()
})
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

function progressWith(overrides: {
  ring_enabled?: boolean
  badges_enabled?: boolean
  days_read_this_week?: number
  ring_goal_days?: number
  badges?: { id: string; name: string; description: string; earned_at: string }[]
}) {
  return {
    data: {
      badges: overrides.badges ?? [],
      books: [],
      totals: { books_finished: 0, endings_found: 0 },
      days_read_this_week: overrides.days_read_this_week ?? 0,
      lifetime_days_read: 0,
      settings: {
        ring_enabled: overrides.ring_enabled ?? false,
        ring_goal_days: overrides.ring_goal_days ?? 3,
        badges_enabled: overrides.badges_enabled ?? false,
        time_capture_paused: false,
      },
    },
  }
}

beforeEach(() => {
  mockGet.mockClear()
  profilesGet.mockReset()
  progressGet.mockReset()
  // Default: progress fetch degrades to the empty/hidden shape (a test that
  // does not care about the ring/badge case need not configure this).
  progressGet.mockResolvedValue(progressWith({}))
  _resetKidProfileFetch()
})

describe('KidNav', () => {
  it('always offers a Switch reader link to the profile picker', async () => {
    profilesGet.mockResolvedValue({ data: { profiles: PROFILES } })
    renderNav()
    const link = await screen.findByRole('link', { name: /switch reader/i })
    expect(link).toHaveAttribute('href', '/kids')
  })

  it('shows whose books these are once the profile loads', async () => {
    profilesGet.mockResolvedValue({ data: { profiles: PROFILES } })
    renderNav('p1')
    expect(await screen.findByText('Mia')).toBeInTheDocument()
  })

  it('still renders the Switch reader link when the profile lookup fails', async () => {
    profilesGet.mockRejectedValue(new Error('offline'))
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
    profilesGet.mockReturnValueOnce(p1Promise)
    profilesGet.mockResolvedValueOnce({ data: { profiles: [p2Profile] } })

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
    profilesGet.mockResolvedValueOnce({ data: { profiles: PROFILES } })
    profilesGet.mockRejectedValueOnce(new Error('offline'))

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

  describe('weekly ring and badge case (W3.4/W3.2)', () => {
    it('hides the ring entirely when the resolved settings say off (e.g. band 3-5 default)', async () => {
      profilesGet.mockResolvedValue({ data: { profiles: PROFILES } })
      progressGet.mockResolvedValue(progressWith({ ring_enabled: false }))
      renderNav()
      await screen.findByText('Mia')
      expect(screen.queryByTestId('weekly-ring')).toBeNull()
    })

    it('shows the ring with the resolved days/goal when enabled', async () => {
      profilesGet.mockResolvedValue({ data: { profiles: PROFILES } })
      progressGet.mockResolvedValue(
        progressWith({ ring_enabled: true, days_read_this_week: 2, ring_goal_days: 3 })
      )
      renderNav()
      const ring = await screen.findByTestId('weekly-ring')
      expect(ring).toHaveAccessibleName('You read on 2 days this week, out of a goal of 3')
    })

    it('hides the Badges button entirely when badges are disabled', async () => {
      profilesGet.mockResolvedValue({ data: { profiles: PROFILES } })
      progressGet.mockResolvedValue(progressWith({ badges_enabled: false }))
      renderNav()
      await screen.findByText('Mia')
      expect(screen.queryByTestId('open-badge-case')).toBeNull()
    })

    it('opens the badge case on tap when badges are enabled', async () => {
      const { default: userEvent } = await import('@testing-library/user-event')
      profilesGet.mockResolvedValue({ data: { profiles: PROFILES } })
      progressGet.mockResolvedValue(
        progressWith({
          badges_enabled: true,
          badges: [{ id: 'first_ending', name: 'First Ending', description: 'x', earned_at: 't' }],
        })
      )
      renderNav()
      const button = await screen.findByTestId('open-badge-case')
      await userEvent.click(button)
      expect(screen.getByText('Your Badges')).toBeInTheDocument()
    })

    it('never shows the ring or badge case when the progress fetch fails', async () => {
      profilesGet.mockResolvedValue({ data: { profiles: PROFILES } })
      progressGet.mockRejectedValue(new Error('offline'))
      renderNav()
      await screen.findByText('Mia')
      expect(screen.queryByTestId('weekly-ring')).toBeNull()
      expect(screen.queryByTestId('open-badge-case')).toBeNull()
    })
  })
})
