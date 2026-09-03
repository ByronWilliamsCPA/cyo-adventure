import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OutstandingDecisionsPage } from './OutstandingDecisionsPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const DECISIONS_PATH = '/v1/admin/outstanding-decisions'

type Item = Record<string, unknown>

function moderationRow(overrides: Item = {}): Item {
  return {
    kind: 'moderation',
    storybook_id: 'the-lighthouse-mystery',
    title: 'The Lighthouse Mystery',
    status: 'published',
    version: 3,
    family_id: 'fam-1',
    age_band: '8-11',
    version_created_at: '2026-07-01T12:00:00Z',
    recallable: true,
    moderation: {
      block_findings: 1,
      flag_findings: 0,
      advisory_findings: 4,
      report_unusable: false,
      top_finding: {
        stage: 1,
        source: 'openai',
        category: 'violence',
        node_id: 'n-7',
        verdict: 'block',
        score: 0.62,
        message: 'Graphic injury described in detail.',
      },
    },
    cover: null,
    ...overrides,
  }
}

function coverRow(overrides: Item = {}): Item {
  return {
    kind: 'cover',
    storybook_id: 'the-clocktower-key',
    title: 'The Clocktower Key',
    status: 'published',
    version: 2,
    family_id: 'fam-1',
    age_band: '5-7',
    version_created_at: '2026-06-01T12:00:00Z',
    recallable: true,
    moderation: null,
    cover: { cover_status: 'pending_review', child_facing: true },
    ...overrides,
  }
}

function mockList(items: Item[]) {
  mockGet.mockImplementation((path: string) => {
    if (path === DECISIONS_PATH) return Promise.resolve({ data: { items } })
    throw new Error(`unexpected GET path "${path}"`)
  })
}

function renderPage() {
  return render(
    <MemoryRouter>
      <OutstandingDecisionsPage />
    </MemoryRouter>
  )
}

describe('OutstandingDecisionsPage', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
  })

  it('says nothing is outstanding only when the list is actually empty', async () => {
    mockList([])
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('no-outstanding-decisions')).toBeInTheDocument()
    })
  })

  it('shows an error instead of an empty state when the load fails', async () => {
    // The distinction is the point: an outage that rendered "Nothing
    // outstanding" would read as a clean bill of health for every published
    // book, which under ADR-005 is a safety claim nobody made.
    mockGet.mockRejectedValue(new Error('boom'))
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('no-outstanding-decisions')).not.toBeInTheDocument()
  })

  it('states the block count and the top finding for a moderation row', async () => {
    mockList([moderationRow()])
    renderPage()
    const row = await screen.findByTestId('moderation:the-lighthouse-mystery:3')
    expect(within(row).getByText(/1 block on a published book/)).toBeInTheDocument()
    expect(within(row).getByText(/Graphic injury described in detail/)).toBeInTheDocument()
    // Owner ruling 3: advisories are counted and reachable, never part of the
    // headline. So the count appears, but not in the decision sentence.
    expect(within(row).getByText(/4 advisory/)).toBeInTheDocument()
    expect(within(row).queryByText(/4 advisory on a published book/)).not.toBeInTheDocument()
  })

  it('describes an unreadable report as a missing verdict, not as no findings', async () => {
    mockList([
      moderationRow({
        moderation: {
          block_findings: 0,
          flag_findings: 0,
          advisory_findings: 0,
          report_unusable: true,
          top_finding: null,
        },
      }),
    ])
    renderPage()
    const row = await screen.findByTestId('moderation:the-lighthouse-mystery:3')
    expect(within(row).getByText(/no usable verdict/)).toBeInTheDocument()
    expect(within(row).queryByText(/0 block/)).not.toBeInTheDocument()
  })

  it('tells the admin when a child-facing book is on the shelf without its cover', async () => {
    mockList([
      coverRow(),
      coverRow({
        storybook_id: 'other',
        cover: { cover_status: 'pending_review', child_facing: false },
      }),
    ])
    renderPage()
    const shelved = await screen.findByTestId('cover:the-clocktower-key:2')
    expect(within(shelved).getByText(/on the shelf without it/)).toBeInTheDocument()
    const notShelved = screen.getByTestId('cover:other:2')
    expect(within(notShelved).getByText(/Cover art is waiting for approval$/)).toBeInTheDocument()
    // Deletion-sensitive: the badge must agree with the sentence next to it.
    // Both cover rows used to read "Advisory", which says no action is needed
    // while the shelved row's own headline says a child can reach the book now.
    expect(within(shelved).getByText('Flagged')).toBeInTheDocument()
    expect(within(notShelved).getByText('Advisory')).toBeInTheDocument()
  })

  it('offers recall only on a recallable moderation row', async () => {
    mockList([
      moderationRow(),
      moderationRow({ storybook_id: 'not-recallable', recallable: false }),
      coverRow(),
    ])
    renderPage()
    const recallable = await screen.findByTestId('moderation:the-lighthouse-mystery:3')
    expect(
      within(recallable).getByRole('button', { name: /recall to review/i })
    ).toBeInTheDocument()
    // A cover row is never a recall candidate, and neither is a row whose
    // status the server says cannot transition: the button set is derived from
    // the API's `recallable`, never from the status string in the client.
    for (const testId of ['moderation:not-recallable:3', 'cover:the-clocktower-key:2']) {
      const row = screen.getByTestId(testId)
      expect(
        within(row).queryByRole('button', { name: /recall to review/i })
      ).not.toBeInTheDocument()
    }
  })

  it('links both kinds of row to the same review page', async () => {
    mockList([moderationRow(), coverRow()])
    renderPage()
    const moderation = await screen.findByTestId('moderation:the-lighthouse-mystery:3')
    expect(within(moderation).getByRole('link', { name: /open review/i })).toHaveAttribute(
      'href',
      '/admin/review/the-lighthouse-mystery'
    )
    const cover = screen.getByTestId('cover:the-clocktower-key:2')
    expect(within(cover).getByRole('link', { name: /open review/i })).toHaveAttribute(
      'href',
      '/admin/review/the-clocktower-key'
    )
  })

  it('warns that an already-downloaded copy survives the recall', async () => {
    mockList([moderationRow()])
    renderPage()
    const row = await screen.findByTestId('moderation:the-lighthouse-mystery:3')
    await userEvent.click(within(row).getByRole('button', { name: /recall to review/i }))
    // Pinned because offline eviction is reconcile-on-fetch (offline/revocation.ts):
    // an operator who read recall as immediate removal would use it as an
    // incident response it cannot serve.
    expect(screen.getByText(/keeps its copy until it next syncs its library/)).toBeInTheDocument()
  })

  it('sends the chosen reason code and re-fetches the list on success', async () => {
    mockList([moderationRow()])
    mockPost.mockResolvedValue({
      data: { storybook_id: 'the-lighthouse-mystery', status: 'in_review' },
    })
    renderPage()
    const row = await screen.findByTestId('moderation:the-lighthouse-mystery:3')
    await userEvent.click(within(row).getByRole('button', { name: /recall to review/i }))
    await userEvent.selectOptions(screen.getByLabelText(/reason/i), 'safety_concern')
    mockList([])
    await userEvent.click(screen.getByRole('button', { name: /confirm recall/i }))
    expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/the-lighthouse-mystery/recall', {
      reason_code: 'safety_concern',
    })
    // The list is re-read rather than patched: which rows survive a recall is a
    // server-side decision this page does not reimplement.
    await waitFor(() => {
      expect(screen.getByTestId('no-outstanding-decisions')).toBeInTheDocument()
    })
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('keeps the dialog open and reports the failure when the recall is rejected', async () => {
    mockList([moderationRow()])
    mockPost.mockRejectedValue(new Error('409'))
    renderPage()
    const row = await screen.findByTestId('moderation:the-lighthouse-mystery:3')
    await userEvent.click(within(row).getByRole('button', { name: /recall to review/i }))
    await userEvent.click(screen.getByRole('button', { name: /confirm recall/i }))
    await waitFor(() => {
      expect(screen.getByText(/could not recall this book/i)).toBeInTheDocument()
    })
    // Still open, and the list was not re-read: a failed recall must not look
    // like a successful one that produced an empty list.
    expect(screen.getByRole('button', { name: /confirm recall/i })).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('defaults the reason to the threshold change this surface exists for', async () => {
    mockList([moderationRow()])
    renderPage()
    const row = await screen.findByTestId('moderation:the-lighthouse-mystery:3')
    await userEvent.click(within(row).getByRole('button', { name: /recall to review/i }))
    expect(screen.getByLabelText(/reason/i)).toHaveValue('threshold_change')
  })
})
