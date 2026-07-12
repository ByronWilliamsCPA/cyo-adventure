import { render, screen } from '@testing-library/react'
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
    expect(screen.getByText(/2 flagged/i)).toBeInTheDocument()
    expect(screen.getByText('Clean')).toBeInTheDocument()
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
