import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ConsolePage } from './ConsolePage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

// Default every pre-existing case to a guardian principal: this page's own
// content (the review queue) is admin-only and does not depend on the
// mocked role, but the admin-only RequestStoryForm embed (WS-B PR2) does, so
// defaulting to guardian gates it out of every case below except the two
// dedicated admin-embed tests, matching its own isolated coverage in
// RequestStoryForm.test.tsx.
const mockUseAuth = vi.fn()
vi.mock('../auth/useAuth', () => ({
  useAuth: (): unknown => mockUseAuth(),
}))

function principal(role: 'guardian' | 'admin') {
  return { principal: { subject: 's', role, familyId: 'f', profileIds: [] } }
}

const FLAGGED = {
  storybook_id: 'flag-1',
  title: 'Scary Tale',
  status: 'in_review',
  version: 1,
  screened: true,
  flagged_count: 2,
  summary: { count: 2, hard_block: false, soft_flag: true, repaired: false, reviewer_independent: true },
}
const READY = {
  storybook_id: 'ready-1',
  title: 'Gentle Tale',
  status: 'in_review',
  version: 1,
  screened: true,
  flagged_count: 0,
  summary: { count: 0, hard_block: false, soft_flag: false, repaired: false, reviewer_independent: false },
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ConsolePage />
    </MemoryRouter>
  )
}

// The console loads /v1/review-queue and /v1/generation-jobs in one Promise.all,
// so a realistic mock must branch on the URL: returning items-shaped data for
// the jobs endpoint would throw in stillProcessing (res.data.jobs undefined).
function mockQueue(
  items: unknown[],
  jobs: unknown[] = [],
  profiles: unknown[] = [{ id: 'p1' }],
  families: unknown[] = []
) {
  mockGet.mockImplementation((url: string) =>
    url === '/v1/generation-jobs'
      ? Promise.resolve({ data: { jobs } })
      : url === '/v1/profiles'
        ? Promise.resolve({ data: { profiles } })
        : url === '/v1/admin/families'
          ? Promise.resolve({ data: { families } })
          : Promise.resolve({ data: { items } })
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockQueue([FLAGGED, READY])
  mockPost.mockReset()
  mockUseAuth.mockReset()
  mockUseAuth.mockReturnValue(principal('guardian'))
})

describe('ConsolePage', () => {
  it('lists flagged and ready stories with severity pills', async () => {
    renderPage()
    expect(await screen.findByText('Scary Tale')).toBeInTheDocument()
    expect(screen.getByText('Gentle Tale')).toBeInTheDocument()
    expect(screen.getByText(/2 flagged/i)).toBeInTheDocument()
    expect(screen.getByText('Clean')).toBeInTheDocument()
  })

  it('orders the sections Flagged, then Ready, then Still processing', async () => {
    renderPage()
    await screen.findByText('Scary Tale')
    const headings = screen
      .getAllByRole('heading', { level: 2 })
      .map((heading) => heading.textContent)
    expect(headings).toEqual([
      'Flagged (review carefully)',
      'Ready to review',
      'Still processing',
    ])
  })

  it('buckets a never-screened story under Flagged with an Unscreened pill', async () => {
    mockQueue([
      { ...READY, storybook_id: 'raw-1', title: 'Raw Tale', screened: false, summary: null },
    ])
    renderPage()
    expect(await screen.findByText('Raw Tale')).toBeInTheDocument()
    expect(screen.getByText('Unscreened')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Flagged (review carefully)' })
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Ready to review' })
    ).not.toBeInTheDocument()
  })

  it('links each row to its review detail page', async () => {
    renderPage()
    const link = await screen.findByRole('link', { name: /Scary Tale/i })
    expect(link).toHaveAttribute('href', '/guardian/review/flag-1')
  })

  it('shows the empty state when nothing is pending', async () => {
    mockQueue([])
    renderPage()
    expect(await screen.findByText(/Nothing to review/i)).toBeInTheDocument()
  })

  it('nudges a childless family to add a profile in the empty state', async () => {
    mockQueue([], [], [])
    renderPage()
    const link = await screen.findByRole('link', { name: /add a child profile/i })
    expect(link).toHaveAttribute('href', '/guardian/profiles')
  })

  it('does not nudge to add a profile when the family already has children', async () => {
    mockQueue([]) // default mock has one child profile
    renderPage()
    await screen.findByText(/Nothing to review/i)
    expect(
      screen.queryByRole('link', { name: /add a child profile/i })
    ).not.toBeInTheDocument()
  })

  it('renders queued/running jobs in the Still processing section', async () => {
    mockQueue(
      [],
      [{ id: 'j1', status: 'running', title: 'Brewing a Tale', premise_snippet: 'x' }]
    )
    renderPage()
    expect(await screen.findByText('Brewing a Tale')).toBeInTheDocument()
    expect(screen.getByText('Processing…')).toBeInTheDocument()
  })

  it('shows the safety-reviewer notice on a 403 (plain guardian token)', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    renderPage()
    expect(await screen.findByText(/safety reviewer/i)).toBeInTheDocument()
  })

  it('shows a generic error when the queue fails for another reason', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })

  it('renders the admin request-a-story form for an admin principal', async () => {
    mockUseAuth.mockReturnValue(principal('admin'))
    mockQueue([FLAGGED, READY], [], [{ id: 'p1' }], [{ id: 'fam-1', name: 'The Ambers' }])
    renderPage()
    expect(await screen.findByLabelText(/what should the story be about/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/family/i)).toBeInTheDocument()
  })

  it('does not render the request-a-story form for a guardian principal', async () => {
    renderPage()
    await screen.findByText('Scary Tale')
    expect(screen.queryByLabelText(/what should the story be about/i)).not.toBeInTheDocument()
  })

  it('shows moderation admin links for admins only', async () => {
    mockUseAuth.mockReturnValue(principal('admin'))
    renderPage()
    expect(
      await screen.findByRole('link', { name: /moderation dashboard/i })
    ).toHaveAttribute('href', '/guardian/moderation-dashboard')
    expect(
      screen.getByRole('link', { name: /moderation thresholds/i })
    ).toHaveAttribute('href', '/guardian/moderation-thresholds')
  })

  it('hides moderation admin links from plain guardians', async () => {
    mockUseAuth.mockReturnValue(principal('guardian'))
    renderPage()
    // ConsolePage's own heading is "Review queue", not "Console"; wait on the
    // same settled-state query the guardian-role form test above uses.
    await screen.findByText('Scary Tale')
    expect(
      screen.queryByRole('link', { name: /moderation dashboard/i })
    ).not.toBeInTheDocument()
  })
})
