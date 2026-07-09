import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ModerationDashboardPage } from './ModerationDashboardPage'

const mockGet = vi.fn()
const mockPut = vi.fn()
const fakeApi = { get: mockGet, put: mockPut }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

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

function mockGetByPath(overrides: Record<string, unknown> = {}) {
  mockGet.mockImplementation((path: string) => {
    if (path === '/v1/admin/moderation/suggestions') {
      return Promise.resolve({ data: overrides.suggestions ?? SUGGESTIONS_VIEW })
    }
    return Promise.resolve({ data: overrides.dashboard ?? DASHBOARD_VIEW })
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
})
