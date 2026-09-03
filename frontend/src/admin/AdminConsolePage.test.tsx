import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
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
  report_unusable: false,
  block_findings: 0,
  flag_findings: 0,
  advisory_findings: 0,
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
  report_unusable: false,
  block_findings: 0,
  flag_findings: 0,
  advisory_findings: 0,
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
  report_unusable: false,
  block_findings: 0,
  flag_findings: 0,
  advisory_findings: 0,
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
  report_unusable: false,
  block_findings: 0,
  flag_findings: 0,
  advisory_findings: 0,
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
    // `RS-A3`: FLAGGED carries no tiered counts, so the badge falls back to
    // flagged_count and must NAME it. That field counts occurrences, which is
    // a different number from the tiers, and "2 flags" claimed otherwise.
    expect(screen.getByText('2 flagged occurrences')).toBeInTheDocument()
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
    // row already shows, not a duplicated/independent computation.
    expect(within(dialog).getByText('2 flagged occurrences')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: /^Close$/ }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('omits age band and themes from the dialog when a queue item carries neither', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /View details for Gentle Tale/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByText('Age band')).not.toBeInTheDocument()
    expect(within(dialog).queryByText('Themes')).not.toBeInTheDocument()
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
    expect(screen.getByText('1 flagged occurrence')).toBeInTheDocument()
    expect(screen.getByText('Repaired')).toBeInTheDocument()
  })

  it('shows a moderation-unavailable badge and keeps the book in the flagged bucket', async () => {
    mockQueue([{ ...FLAGGED, flagged_count: 0, report_unusable: true }])
    renderPage()
    expect(await screen.findByText(/moderation unavailable/i)).toBeInTheDocument()
    // No role="region" on the bucket; it is headed by an <h2>, so scope to
    // that heading's own console-group container the way the page renders
    // buckets, not a landmark role that does not exist here.
    const flaggedHeading = screen.getByRole('heading', { name: /flagged \(review carefully\)/i })
    const flaggedSection = flaggedHeading.closest('.console-group')
    expect(flaggedSection).not.toBeNull()
    expect(within(flaggedSection as HTMLElement).getByText(FLAGGED.title)).toBeInTheDocument()
  })

  it('renders tiered counts instead of a flat flag count', async () => {
    mockQueue([
      { ...FLAGGED, block_findings: 1, flag_findings: 3, advisory_findings: 47, flagged_count: 51 },
    ])
    renderPage()
    expect(await screen.findByText('1 block · 3 flags · 47 advisories')).toBeInTheDocument()
    expect(screen.queryByText('51 flags')).not.toBeInTheDocument()
    // `RS-A3`: the occurrence fallback must not ALSO render once the tiers are
    // known, or the row shows two numbers for one book again.
    expect(screen.queryByText(/flagged occurrence/)).not.toBeInTheDocument()
  })

  it('pluralizes each tier independently rather than hard-coding one form', async () => {
    // `RS-A3`: the hand-rolled label read "2 block" and "1 flags"; both arms
    // of every tier's plural are now the shared pluralize's problem, so this
    // pins the singular block/advisory forms the old code could not produce.
    mockQueue([
      { ...FLAGGED, block_findings: 2, flag_findings: 1, advisory_findings: 1, flagged_count: 4 },
    ])
    renderPage()
    expect(await screen.findByText('2 blocks · 1 flag · 1 advisory')).toBeInTheDocument()
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

  it('sorts the flagged bucket hard blocks first, then report_unusable, then flag count desc', async () => {
    const unusable = {
      ...FLAGGED,
      storybook_id: 'unusable-1',
      title: 'Unusable Tale',
      flagged_count: 0,
      report_unusable: true,
    }
    const highCount = {
      ...FLAGGED,
      storybook_id: 'high-1',
      title: 'High Flag Tale',
      flagged_count: 9,
      summary: { ...FLAGGED.summary, count: 9 },
    }
    const block = { ...HARD_BLOCKED, storybook_id: 'block-1', title: 'Block Tale' }
    // Response order deliberately scrambled so the assertion proves the sort,
    // not incidental backend ordering.
    mockQueue([highCount, unusable, block])
    renderPage()
    await screen.findByText('Block Tale')
    const titles = screen.getAllByRole('link').map((link) => link.textContent)
    expect(titles).toEqual([
      expect.stringContaining('Block Tale'),
      expect.stringContaining('Unusable Tale'),
      expect.stringContaining('High Flag Tale'),
    ])
  })

  it('ranks the flagged bucket by tier weight, not by occurrence count', async () => {
    // `RS-A7`: this is the case the old flagged_count tiebreak got backwards.
    // None of the three trips summary.hard_block, so the tier comparison is
    // the only thing that can separate them. The counts are chosen so each
    // book wins on a DIFFERENT tier and loses on the ones above it: swapping
    // any two comparisons, or reinstating the occurrence-count tiebreak,
    // reorders this list.
    const oneBlock = {
      ...FLAGGED,
      storybook_id: 'block-tier-1',
      title: 'One Block Tale',
      flagged_count: 1,
      block_findings: 1,
      flag_findings: 0,
      advisory_findings: 0,
    }
    const manyFlags = {
      ...FLAGGED,
      storybook_id: 'flag-many-1',
      title: 'Many Flag Tale',
      flagged_count: 5,
      block_findings: 0,
      flag_findings: 5,
      advisory_findings: 0,
    }
    // 380 is an OCCURRENCE count: one merged advisory fanned across the story.
    // Under the old sort this book led the queue.
    const manyAdvisories = {
      ...FLAGGED,
      storybook_id: 'advisory-many-1',
      title: 'Many Advisory Tale',
      flagged_count: 380,
      block_findings: 0,
      flag_findings: 0,
      advisory_findings: 8,
    }
    // Response order is the old sort's order, so passing cannot be incidental.
    mockQueue([manyAdvisories, manyFlags, oneBlock])
    renderPage()
    await screen.findByText('One Block Tale')
    const titles = screen.getAllByRole('link').map((link) => link.textContent)
    expect(titles).toEqual([
      expect.stringContaining('One Block Tale'),
      expect.stringContaining('Many Flag Tale'),
      expect.stringContaining('Many Advisory Tale'),
    ])
  })

  it('ranks a flag above an advisory at equal block count', async () => {
    const oneFlag = {
      ...FLAGGED,
      storybook_id: 'flag-tier-1',
      title: 'One Flag Tier Tale',
      flagged_count: 1,
      block_findings: 0,
      flag_findings: 1,
      advisory_findings: 0,
    }
    const threeAdvisories = {
      ...FLAGGED,
      storybook_id: 'advisory-tier-1',
      title: 'Three Advisory Tier Tale',
      flagged_count: 3,
      block_findings: 0,
      flag_findings: 0,
      advisory_findings: 3,
    }
    mockQueue([threeAdvisories, oneFlag])
    renderPage()
    await screen.findByText('One Flag Tier Tale')
    const titles = screen.getAllByRole('link').map((link) => link.textContent)
    expect(titles).toEqual([
      expect.stringContaining('One Flag Tier Tale'),
      expect.stringContaining('Three Advisory Tier Tale'),
    ])
  })

  it('names the top finding on the queue row', async () => {
    const withReason = {
      ...HARD_BLOCKED,
      storybook_id: 'reason-1',
      title: 'Cistern Tale',
      top_finding: {
        stage: 2,
        source: 'safety',
        category: 'violence',
        node_id: 'n42',
        verdict: 'block',
        score: 0.91,
        message: 'The cistern passage describes a drowning in graphic detail.',
        severity: 'high',
        concern: 'graphic peril',
      },
    }
    mockQueue([withReason])
    renderPage()
    const row = within(await screen.findByRole('link', { name: /Cistern Tale/ }))
    // The concern, not the raw category, is what the detail page leads with.
    expect(row.getByText('graphic peril')).toBeInTheDocument()
    expect(
      row.getByText('The cistern passage describes a drowning in graphic detail.')
    ).toBeInTheDocument()
  })

  it('falls back to the finding category when the report records no concern', async () => {
    const withoutConcern = {
      ...HARD_BLOCKED,
      storybook_id: 'reason-2',
      title: 'Uncategorized Tale',
      top_finding: {
        stage: 2,
        source: 'safety',
        category: 'self_harm',
        node_id: 'n7',
        verdict: 'block',
        score: 0.8,
        message: 'A character talks about hurting themselves.',
      },
    }
    mockQueue([withoutConcern])
    renderPage()
    const row = within(await screen.findByRole('link', { name: /Uncategorized Tale/ }))
    expect(row.getByText('self_harm')).toBeInTheDocument()
  })

  it('shows no reason line on a row the backend sent no top finding for', async () => {
    // Two absences to cover: a clean book (nothing to name) and a payload
    // cached before the field existed. Both must render nothing rather than
    // an empty separator or a guessed reason.
    const clean = { ...READY, storybook_id: 'clean-1', title: 'Clean Tale', top_finding: null }
    mockQueue([clean, FLAGGED])
    renderPage()
    const cleanRow = await screen.findByRole('link', { name: /Clean Tale/ })
    expect(cleanRow.querySelector('.console-row__reason')).toBeNull()
    // FLAGGED carries no top_finding key at all, the legacy-payload shape.
    const legacyRow = screen.getByRole('link', { name: /Scary Tale/ })
    expect(legacyRow.querySelector('.console-row__reason')).toBeNull()
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

  // The three ways the jobs list comes back empty are not the same fact, and
  // the console used to render the same sentence for all three. These two
  // tests pin the split: only a real failure may say "could not load".
  it('says the jobs load failed rather than asserting nothing is generating', async () => {
    mockGet.mockImplementation((url: string) =>
      url === '/v1/generation-jobs'
        ? Promise.reject(new Error('jobs endpoint down'))
        : Promise.resolve({ data: { items: [READY] } })
    )
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    renderPage()
    expect(await screen.findByText('Gentle Tale')).toBeInTheDocument()
    expect(screen.getByText(/Could not load what is generating right now/i)).toBeInTheDocument()
    expect(screen.queryByText(/No stories are generating right now/i)).not.toBeInTheDocument()
    errorSpy.mockRestore()
  })

  it('keeps the plain empty state for a 403, the expected admin outcome', async () => {
    // Guardian-only endpoint; the admin reviewer who is this console's primary
    // user always 403s here. Treating that as degraded would show a permanent
    // failure notice on every normal admin visit.
    // Object.assign onto a real Error rather than a bare object literal:
    // @typescript-eslint/prefer-promise-reject-errors rejects the literal at an
    // inline Promise.reject, and axios's isAxiosError only reads the flag.
    const forbidden = Object.assign(new Error('forbidden'), {
      isAxiosError: true,
      response: { status: 403 },
    })
    mockGet.mockImplementation((url: string) =>
      url === '/v1/generation-jobs'
        ? Promise.reject(forbidden)
        : Promise.resolve({ data: { items: [READY] } })
    )
    renderPage()
    expect(await screen.findByText('Gentle Tale')).toBeInTheDocument()
    expect(screen.getByText(/No stories are generating right now/i)).toBeInTheDocument()
    expect(
      screen.queryByText(/Could not load what is generating right now/i)
    ).not.toBeInTheDocument()
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
