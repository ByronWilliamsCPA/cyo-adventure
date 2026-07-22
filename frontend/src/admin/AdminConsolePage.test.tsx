import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminConsolePage } from './AdminConsolePage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const FLAGGED = {
  storybook_id: 'flag-1',
  title: 'Scary Tale',
  status: 'in_review',
  version: 1,
  screened: true,
  flagged_count: 2,
  summary: {
    count: 2,
    hard_block: false,
    soft_flag: true,
    repaired: false,
    reviewer_independent: true,
  },
  age_band: '8-11',
  themes: ['adventure'],
  content_flags: { violence: 'moderate', scariness: 'mild', peril: 'none' },
}
const READY = {
  storybook_id: 'ready-1',
  title: 'Gentle Tale',
  status: 'in_review',
  version: 1,
  screened: true,
  flagged_count: 0,
  summary: {
    count: 0,
    hard_block: false,
    soft_flag: false,
    repaired: false,
    reviewer_independent: false,
  },
}
const HARD_BLOCKED = {
  storybook_id: 'block-1',
  title: 'Grim Tale',
  status: 'in_review',
  version: 1,
  screened: true,
  flagged_count: 1,
  summary: {
    count: 1,
    hard_block: true,
    soft_flag: false,
    repaired: false,
    reviewer_independent: true,
  },
}
const REPAIRED = {
  storybook_id: 'repair-1',
  title: 'Patched Tale',
  status: 'in_review',
  version: 1,
  screened: true,
  flagged_count: 1,
  summary: {
    count: 1,
    hard_block: false,
    soft_flag: true,
    repaired: true,
    reviewer_independent: true,
  },
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminConsolePage />
    </MemoryRouter>
  )
}

// The console loads /v1/review-queue and /v1/generation-jobs in one Promise.all,
// so a realistic mock must branch on the URL: returning items-shaped data for
// the jobs endpoint would throw in stillProcessing (res.data.jobs undefined).
function mockQueue(items: unknown[], jobs: unknown[] = []) {
  mockGet.mockImplementation((url: string) =>
    url === '/v1/generation-jobs'
      ? Promise.resolve({ data: { jobs } })
      : Promise.resolve({ data: { items } })
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockQueue([FLAGGED, READY])
  mockPost.mockReset()
})

describe('AdminConsolePage', () => {
  it('lists flagged and ready stories with severity pills', async () => {
    renderPage()
    expect(await screen.findByText('Scary Tale')).toBeInTheDocument()
    expect(screen.getByText('Gentle Tale')).toBeInTheDocument()
    expect(screen.getByText('2 flags')).toBeInTheDocument()
    expect(screen.getByText('Clean')).toBeInTheDocument()
  })

  it('opens a book-details dialog with age band, themes, content flags, and the queue moderation badge', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /View details for Scary Tale/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Ages 8-11')).toBeInTheDocument()
    expect(within(dialog).getByText('adventure')).toBeInTheDocument()
    expect(within(dialog).getByText(/Violence: moderate/)).toBeInTheDocument()
    // The dialog's moderation slot reuses the same SeverityBadges the queue
    // row already shows: "2 flags", not a duplicated/independent computation.
    expect(within(dialog).getByText('2 flags')).toBeInTheDocument()
  })

  it('shows a Hard block badge (not a flag count) on a hard-blocked row', async () => {
    mockQueue([HARD_BLOCKED])
    renderPage()
    expect(await screen.findByText('Grim Tale')).toBeInTheDocument()
    expect(screen.getByText('Hard block')).toBeInTheDocument()
    expect(screen.queryByText(/\d+ flags?/)).not.toBeInTheDocument()
  })

  it('stacks a Repaired badge beside the flag count and uses the singular form', async () => {
    mockQueue([REPAIRED])
    renderPage()
    expect(await screen.findByText('Patched Tale')).toBeInTheDocument()
    expect(screen.getByText('1 flag')).toBeInTheDocument()
    expect(screen.getByText('Repaired')).toBeInTheDocument()
  })

  it('sorts the flagged bucket hard blocks first, then flag count desc, stable within ties', async () => {
    const softOne = {
      ...FLAGGED,
      storybook_id: 'soft-1',
      title: 'One Flag Tale',
      flagged_count: 1,
      summary: { ...FLAGGED.summary, count: 1 },
    }
    const softThree = {
      ...FLAGGED,
      storybook_id: 'soft-3',
      title: 'Three Flag Tale',
      flagged_count: 3,
      summary: { ...FLAGGED.summary, count: 3 },
    }
    const blockA = { ...HARD_BLOCKED, storybook_id: 'block-a', title: 'Block A Tale' }
    const blockB = { ...HARD_BLOCKED, storybook_id: 'block-b', title: 'Block B Tale' }
    // Response order deliberately scrambled; blockA arriving before blockB
    // pins stability (equal severity keeps backend order).
    mockQueue([softOne, blockA, softThree, blockB])
    renderPage()
    await screen.findByText('Block A Tale')
    const titles = screen.getAllByRole('link').map((link) => link.textContent)
    expect(titles).toEqual([
      expect.stringContaining('Block A Tale'),
      expect.stringContaining('Block B Tale'),
      expect.stringContaining('Three Flag Tale'),
      expect.stringContaining('One Flag Tale'),
    ])
  })

  it('orders the sections Flagged, then Ready, then Still processing', async () => {
    renderPage()
    await screen.findByText('Scary Tale')
    const headings = screen
      .getAllByRole('heading', { level: 2 })
      .map((heading) => heading.textContent)
    expect(headings).toEqual(['Flagged (review carefully)', 'Ready to review', 'Still processing'])
  })

  it('buckets a never-screened story under Flagged with an Unscreened pill', async () => {
    mockQueue([
      { ...READY, storybook_id: 'raw-1', title: 'Raw Tale', screened: false, summary: null },
    ])
    renderPage()
    expect(await screen.findByText('Raw Tale')).toBeInTheDocument()
    expect(screen.getByText('Unscreened')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Flagged (review carefully)' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Ready to review' })).not.toBeInTheDocument()
  })

  it('links each row to its review detail page under /admin', async () => {
    renderPage()
    const link = await screen.findByRole('link', { name: /Scary Tale/i })
    expect(link).toHaveAttribute('href', '/admin/review/flag-1')
  })

  it('shows age-band and waiting-time triage metadata on a row (UX-A3)', async () => {
    mockQueue([
      {
        ...FLAGGED,
        age_band: '6-8',
        waiting_since: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      },
    ])
    renderPage()
    expect(await screen.findByText('Ages 6-8')).toBeInTheDocument()
    expect(screen.getByText(/Waiting 2 hours ago/i)).toBeInTheDocument()
  })

  it('passes the flagged bucket order to the detail page for auto-advance (UX-A1)', async () => {
    renderPage()
    // The row links carry the queue via router state, exercised end-to-end by
    // ReviewDetailPage.test.tsx; here we assert the link still points at detail.
    const link = await screen.findByRole('link', { name: /Scary Tale/i })
    expect(link).toHaveAttribute('href', '/admin/review/flag-1')
  })

  it('shows the empty state when nothing is pending', async () => {
    mockQueue([])
    renderPage()
    expect(await screen.findByText(/Nothing to review/i)).toBeInTheDocument()
  })

  it('renders queued/running jobs in the Still processing section', async () => {
    mockQueue([], [{ id: 'j1', status: 'running', title: 'Brewing a Tale', premise_snippet: 'x' }])
    renderPage()
    expect(await screen.findByText('Brewing a Tale')).toBeInTheDocument()
    expect(screen.getByText('Processing…')).toBeInTheDocument()
  })

  it('shows an Updated HH:MM label and refetches on Refresh without a reload', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Scary Tale')
    expect(screen.getByText(/^Updated \d{2}:\d{2}$/)).toBeInTheDocument()
    mockQueue([READY])
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    await waitFor(() => expect(screen.queryByText('Scary Tale')).not.toBeInTheDocument())
    expect(screen.getByText('Gentle Tale')).toBeInTheDocument()
    expect(screen.getByText(/^Updated \d{2}:\d{2}$/)).toBeInTheDocument()
  })

  it('disables the Refresh button while the refetch is in flight', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Scary Tale')
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    mockGet.mockImplementation(async (url: string) => {
      await gate
      return url === '/v1/generation-jobs' ? { data: { jobs: [] } } : { data: { items: [READY] } }
    })
    const button = screen.getByRole('button', { name: 'Refresh' })
    await user.click(button)
    expect(button).toBeDisabled()
    release()
    await waitFor(() => expect(button).toBeEnabled())
    expect(screen.queryByText('Scary Tale')).not.toBeInTheDocument()
  })

  it('keeps the loaded queue behind an inline alert when a refresh fails', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Scary Tale')
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Refresh failed/i)
    expect(screen.getByText('Scary Tale')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled()
  })

  it('fails closed to the no-access notice when a refresh 403s (capability revoked)', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Scary Tale')
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(await screen.findByText(/does not have review access/i)).toBeInTheDocument()
    expect(screen.queryByText('Scary Tale')).not.toBeInTheDocument()
  })

  it('filters every bucket by case-insensitive title substring', async () => {
    const user = userEvent.setup()
    mockQueue(
      [FLAGGED, READY],
      [{ id: 'j1', status: 'queued', title: 'Gentle Job', premise_snippet: 'x' }]
    )
    renderPage()
    await screen.findByText('Scary Tale')
    await user.type(screen.getByLabelText('Search by title'), 'GENTLE')
    expect(screen.queryByText('Scary Tale')).not.toBeInTheDocument()
    expect(screen.getByText('Gentle Tale')).toBeInTheDocument()
    expect(screen.getByText('Gentle Job')).toBeInTheDocument()
    // The flagged bucket has no matches, so its heading disappears rather
    // than rendering an empty group.
    expect(
      screen.queryByRole('heading', { name: 'Flagged (review carefully)' })
    ).not.toBeInTheDocument()
  })

  it('shows a no-matches state distinct from the true empty states, and clears', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Scary Tale')
    await user.type(screen.getByLabelText('Search by title'), 'zzz')
    expect(screen.getByText('No matches for "zzz"')).toBeInTheDocument()
    expect(screen.queryByText(/Nothing to review/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/No stories are generating right now/i)).not.toBeInTheDocument()
    await user.clear(screen.getByLabelText('Search by title'))
    expect(screen.getByText('Scary Tale')).toBeInTheDocument()
    expect(screen.queryByText(/No matches for/i)).not.toBeInTheDocument()
  })

  it('shows the no-access notice on a 403 (capability revoked mid-session)', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    renderPage()
    expect(await screen.findByText(/does not have review access/i)).toBeInTheDocument()
  })

  it('shows a generic error when the queue fails for another reason', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })
})
