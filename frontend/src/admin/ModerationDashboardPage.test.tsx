import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ModerationDashboardPage } from './ModerationDashboardPage'

const mockGet = vi.fn()
const mockPut = vi.fn()
const fakeApi = { get: mockGet, put: mockPut }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const DASHBOARD_PATH = '/v1/admin/moderation/dashboard'
const SUGGESTIONS_PATH = '/v1/admin/moderation/suggestions'

const DASHBOARD_VIEW = {
  insights: [
    {
      age_band: '8-11',
      category: 'violence',
      advisory_findings: 2,
      flag_findings: 4,
      decided_versions: 6,
      released_versions: 6,
      override_rate: 1.0,
      last_seen: '2026-07-01T12:00:00Z',
    },
  ],
  recent_changes: [
    {
      occurred_at: '2026-07-02T09:00:00Z',
      event_type: 'threshold_changed',
      entity_id: '8-11:violence',
      payload: {},
    },
  ],
}

const SUGGESTIONS_VIEW = {
  min_decided_versions: 5,
  min_override_rate: 0.8,
  suggestions: [
    {
      age_band: '8-11',
      category: 'violence',
      current_min_verdict: 'flag',
      current_min_score: null,
      suggested_min_verdict: 'block',
      override_rate: 1.0,
      decided_versions: 6,
      released_versions: 6,
    },
  ],
}

// Matches the real dashboard/suggestions paths exactly (rather than treating
// any non-suggestions path as the dashboard call) so a page regression that
// starts hitting the wrong endpoint fails the test instead of silently
// getting the dashboard fixture back.
function mockGetByPath(overrides: Record<string, unknown> = {}) {
  mockGet.mockImplementation((path: string) => {
    if (path === DASHBOARD_PATH) {
      return Promise.resolve({ data: overrides.dashboard ?? DASHBOARD_VIEW })
    }
    if (path === SUGGESTIONS_PATH) {
      return Promise.resolve({ data: overrides.suggestions ?? SUGGESTIONS_VIEW })
    }
    throw new Error(`mockGetByPath: unexpected GET path "${path}"`)
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
})

describe('ModerationDashboardPage', () => {
  it('renders insights, suggestions, and recent changes', async () => {
    mockGetByPath()
    render(<ModerationDashboardPage />)
    // "violence" legitimately appears in three separate sections (the
    // suggestion, the insights table row, and the recent-changes entity id);
    // assert presence rather than a single unique match.
    expect((await screen.findAllByText(/violence/i)).length).toBeGreaterThan(0)
    expect(screen.getByText(/raise to block/i)).toBeInTheDocument()
    expect(screen.getByText(/threshold_changed/)).toBeInTheDocument()

    // Locate the 8-11/violence insights row and assert its override-rate and
    // decided cells render the values the fixture defines, not just that the
    // word "violence" appears somewhere on the page.
    const table = screen.getByRole('table')
    const row = within(table).getByText('violence').closest('tr')
    if (!row) throw new Error('expected a table row for the violence insight')
    const cells = within(row).getAllByRole('cell')
    expect(cells[4]).toHaveTextContent('6') // decided
    expect(cells[6]).toHaveTextContent('100%') // override rate
  })

  it('renders "n/a" for an insight row with a null override rate', async () => {
    mockGetByPath({
      dashboard: {
        insights: [
          {
            age_band: '5-8',
            category: 'toxicity',
            advisory_findings: 1,
            flag_findings: 0,
            decided_versions: 0,
            released_versions: 0,
            override_rate: null,
            last_seen: '2026-07-01T12:00:00Z',
          },
        ],
        recent_changes: [],
      },
      suggestions: { min_decided_versions: 5, min_override_rate: 0.8, suggestions: [] },
    })
    render(<ModerationDashboardPage />)
    const table = await screen.findByRole('table')
    const row = within(table).getByText('toxicity').closest('tr')
    if (!row) throw new Error('expected a table row for the toxicity insight')
    expect(within(row).getByRole('cell', { name: 'n/a' })).toBeInTheDocument()
  })

  it('renders the loading state before the initial data resolves', async () => {
    let resolveDashboard: (value: unknown) => void = () => {
      throw new Error('resolveDashboard called before assignment')
    }
    mockGet.mockImplementation((path: string) => {
      if (path === DASHBOARD_PATH) {
        return new Promise((resolve) => {
          resolveDashboard = resolve
        })
      }
      if (path === SUGGESTIONS_PATH) {
        return Promise.resolve({ data: SUGGESTIONS_VIEW })
      }
      throw new Error(`unexpected GET path: ${path}`)
    })

    render(<ModerationDashboardPage />)
    expect(screen.getByRole('status')).toHaveTextContent(/loading/i)

    await act(async () => {
      resolveDashboard({ data: DASHBOARD_VIEW })
      await Promise.resolve()
    })
    await waitFor(() => {
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    })
  })

  it('shows empty states for insights and recent changes when there are none', async () => {
    mockGetByPath({ dashboard: { insights: [], recent_changes: [] } })
    render(<ModerationDashboardPage />)
    expect(
      await screen.findByText('No moderated books with advisory or flag findings yet.')
    ).toBeInTheDocument()
    expect(screen.getByText('No threshold changes recorded.')).toBeInTheDocument()
  })

  it('applies a suggestion through the thresholds upsert and refreshes', async () => {
    const user = userEvent.setup()
    mockGetByPath()
    mockPut.mockResolvedValue({
      data: {
        age_band: '8-11',
        category: 'violence',
        min_verdict: 'block',
        min_score: null,
      },
    })
    render(<ModerationDashboardPage />)
    await screen.findByText(/raise to block/i)
    await user.click(screen.getByRole('button', { name: /apply/i }))
    expect(mockPut).toHaveBeenCalledWith(
      '/v1/admin/moderation-thresholds/8-11',
      { min_verdict: 'block', min_score: null },
      { params: { category: 'violence' } }
    )
    // Initial load fires 2 GETs; the post-apply refresh fires 2 more.
    expect(mockGet).toHaveBeenCalledTimes(4)
  })

  it('passes a non-null current_min_score through to the PUT payload', async () => {
    const user = userEvent.setup()
    mockGetByPath({
      suggestions: {
        min_decided_versions: 5,
        min_override_rate: 0.8,
        suggestions: [
          {
            age_band: '8-11',
            category: 'violence',
            current_min_verdict: 'flag',
            current_min_score: 0.42,
            suggested_min_verdict: 'block',
            override_rate: 1.0,
            decided_versions: 6,
            released_versions: 6,
          },
        ],
      },
    })
    mockPut.mockResolvedValue({
      data: { age_band: '8-11', category: 'violence', min_verdict: 'block', min_score: 0.42 },
    })
    render(<ModerationDashboardPage />)
    const applyButton = await screen.findByRole('button', {
      name: 'Apply: raise violence (8-11) to block',
    })
    await user.click(applyButton)
    expect(mockPut).toHaveBeenCalledWith(
      '/v1/admin/moderation-thresholds/8-11',
      { min_verdict: 'block', min_score: 0.42 },
      { params: { category: 'violence' } }
    )
  })

  it('keeps per-suggestion apply buttons independent while applies are in flight', async () => {
    const user = userEvent.setup()
    // Two suggestions with distinct suggested verdicts so the two apply
    // buttons have unique accessible names.
    mockGetByPath({
      suggestions: {
        min_decided_versions: 5,
        min_override_rate: 0.8,
        suggestions: [
          ...SUGGESTIONS_VIEW.suggestions,
          {
            age_band: '5-8',
            category: 'toxicity',
            current_min_verdict: 'advisory',
            current_min_score: null,
            suggested_min_verdict: 'flag',
            override_rate: 0.9,
            decided_versions: 10,
            released_versions: 9,
          },
        ],
      },
    })
    // Every PUT hangs until we resolve it explicitly, so both applies can be
    // in flight at once.
    const resolvers: Array<(value: unknown) => void> = []
    mockPut.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvers.push(resolve)
        })
    )
    render(<ModerationDashboardPage />)
    const buttonA = await screen.findByRole('button', {
      name: 'Apply: raise violence (8-11) to block',
    })
    const buttonB = screen.getByRole('button', {
      name: 'Apply: raise toxicity (5-8) to flag',
    })

    await user.click(buttonA)
    // A is in flight: only A's button is disabled; B stays independently
    // clickable.
    expect(buttonA).toBeDisabled()
    expect(buttonB).toBeEnabled()

    await user.click(buttonB)
    // Regression for the shared-state bug: starting B's apply must NOT
    // re-enable A's still-in-flight button.
    expect(buttonA).toBeDisabled()
    expect(buttonB).toBeDisabled()

    // Settle both pending PUTs (and the reload effects they trigger) so the
    // test ends with no dangling state updates.
    await act(async () => {
      for (const resolve of resolvers) {
        resolve({ data: { age_band: 'x', category: 'y', min_verdict: 'block', min_score: null } })
      }
      // Flush the microtask queue so the resolved PUTs' state updates land
      // inside act.
      await Promise.resolve()
    })
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Apply: raise violence (8-11) to block' })
      ).toBeEnabled()
      expect(
        screen.getByRole('button', { name: 'Apply: raise toxicity (5-8) to flag' })
      ).toBeEnabled()
    })
  })

  it('gives two same-verdict suggestions distinct accessible names', async () => {
    mockGetByPath({
      suggestions: {
        min_decided_versions: 5,
        min_override_rate: 0.8,
        suggestions: [
          {
            age_band: '8-11',
            category: 'violence',
            current_min_verdict: 'flag',
            current_min_score: null,
            suggested_min_verdict: 'block',
            override_rate: 1.0,
            decided_versions: 6,
            released_versions: 6,
          },
          {
            age_band: '12-15',
            category: 'graphic-injury',
            current_min_verdict: 'flag',
            current_min_score: null,
            suggested_min_verdict: 'block',
            override_rate: 0.85,
            decided_versions: 8,
            released_versions: 7,
          },
        ],
      },
    })
    render(<ModerationDashboardPage />)
    // Both suggestions target "block", so "raise to block" alone is not a
    // unique accessible name; category + age_band must disambiguate them.
    expect(await screen.findAllByText(/raise to block/i)).toHaveLength(2)
    const buttonViolence = screen.getByRole('button', {
      name: 'Apply: raise violence (8-11) to block',
    })
    const buttonGraphicInjury = screen.getByRole('button', {
      name: 'Apply: raise graphic-injury (12-15) to block',
    })
    expect(buttonViolence).toBeInTheDocument()
    expect(buttonGraphicInjury).toBeInTheDocument()
    expect(buttonViolence).not.toBe(buttonGraphicInjury)
  })

  it('shows an empty state when there are no suggestions', async () => {
    mockGetByPath({
      suggestions: {
        min_decided_versions: 5,
        min_override_rate: 0.8,
        suggestions: [],
      },
    })
    render(<ModerationDashboardPage />)
    expect(await screen.findByText(/no threshold suggestions/i)).toBeInTheDocument()
  })

  it('surfaces a load error', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    render(<ModerationDashboardPage />)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('surfaces an attributed action error and re-enables the button when apply fails', async () => {
    const user = userEvent.setup()
    mockGetByPath()
    mockPut.mockRejectedValue(new Error('boom'))
    render(<ModerationDashboardPage />)
    const applyButton = await screen.findByRole('button', {
      name: 'Apply: raise violence (8-11) to block',
    })
    await user.click(applyButton)

    const alert = await screen.findByRole('alert')
    // The message names which suggestion failed, so two failing suggestions
    // (same or different verdict) are distinguishable in the UI.
    expect(alert).toHaveTextContent(/violence/i)
    expect(alert).toHaveTextContent(/8-11/)

    // The `finally` block always clears the in-flight guard, so the button
    // must be clickable again after the failed apply.
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Apply: raise violence (8-11) to block' })
      ).toBeEnabled()
    })
    // No refresh was attempted after a failed apply.
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('keeps last-good data when a post-apply refresh fails', async () => {
    const user = userEvent.setup()
    let dashboardCallCount = 0
    mockGet.mockImplementation((path: string) => {
      if (path === DASHBOARD_PATH) {
        dashboardCallCount += 1
        if (dashboardCallCount > 1) {
          return Promise.reject(new Error('refresh boom'))
        }
        return Promise.resolve({ data: DASHBOARD_VIEW })
      }
      if (path === SUGGESTIONS_PATH) {
        return Promise.resolve({ data: SUGGESTIONS_VIEW })
      }
      throw new Error(`unexpected GET path: ${path}`)
    })
    mockPut.mockResolvedValue({
      data: { age_band: '8-11', category: 'violence', min_verdict: 'block', min_score: null },
    })
    render(<ModerationDashboardPage />)
    const applyButton = await screen.findByRole('button', {
      name: 'Apply: raise violence (8-11) to block',
    })
    await user.click(applyButton)

    // The apply itself succeeded; only the post-apply refresh GET failed. The
    // page must not blank: the last-good dashboard (table + recent changes)
    // stays rendered, and a dismissible notice appears instead of replacing
    // the page with a full-page error.
    const notice = await screen.findByRole('alert')
    expect(notice).toHaveTextContent(/could not refresh/i)
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText(/threshold_changed/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByText(/could not refresh/i)).not.toBeInTheDocument()
  })
})
