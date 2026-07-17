import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { IntakePage } from './IntakePage'
import { STORY_REQUESTS_CHANGED_EVENT } from './storyRequestQueueApi'

// Stable object reference: a fresh object each call would loop the useMemo/effect.
const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({ useApi: () => fakeApi }))

interface ConceptRequestBody {
  brief: { age_band: string; tone: string; reading_level_target: number }
}

const PROFILE = {
  id: 'p1',
  display_name: 'Reader A',
  age_band: '8-11',
  reading_level_cap: 4,
  avatar: 'fox',
  tts_enabled: false,
  created_at: '2026-07-02T00:00:00Z',
}

function getMock(url: string) {
  if (url === '/v1/profiles') return { data: { profiles: [PROFILE] } }
  if (url === '/v1/generation-jobs') return { data: { jobs: [] } }
  throw new Error(`unexpected GET ${url}`)
}

beforeEach(() => {
  mockGet.mockReset().mockImplementation((url: string) => Promise.resolve(getMock(url)))
  mockPost.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
  // Restores Date.now spies from the request-age tests; mockGet/mockPost get
  // fresh implementations in beforeEach either way.
  vi.restoreAllMocks()
})

// IntakePage now renders a react-router <Link> (the add-child hint), so every
// render needs Router context.
function renderPage() {
  return render(<IntakePage />, { wrapper: MemoryRouter })
}

describe('IntakePage', () => {
  it('shows the add-child hint as a link to profiles when there are no children', async () => {
    mockGet.mockReset().mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [] } })
      if (url === '/v1/generation-jobs') return Promise.resolve({ data: { jobs: [] } })
      throw new Error(`unexpected GET ${url}`)
    })
    renderPage()

    const link = await screen.findByRole('link', { name: /add a child profile first/i })
    expect(link).toHaveAttribute('href', '/guardian/profiles')
  })

  it('posts a concept then enqueues generation with a display-name-free brief', async () => {
    const user = userEvent.setup()
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/concepts') return Promise.resolve({ data: { concept_id: 'c1' } })
      if (url === '/v1/concepts/c1/generate')
        return Promise.resolve({ data: { job_id: 'j1', status: 'queued' } })
      throw new Error(`unexpected POST ${url}`)
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Reader A/i }))
    await user.type(
      screen.getByLabelText(/What's it about/i),
      'A quiet walk through the woods.'
    )
    await user.click(screen.getByRole('button', { name: /^Gentle$/i }))
    await user.click(screen.getByRole('button', { name: /Request Story/i }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/concepts', expect.anything())
    )
    const conceptCall = mockPost.mock.calls.find((c) => c[0] === '/v1/concepts')
    const briefJson = JSON.stringify(conceptCall?.[1])
    expect(briefJson).not.toContain('Reader A')
    const conceptBody = conceptCall?.[1] as ConceptRequestBody | undefined
    expect(conceptBody?.brief.age_band).toBe('8-11')
    expect(conceptBody?.brief.tone).toBe('gentle')
    expect(conceptBody?.brief.reading_level_target).toBe(4)
    expect(mockPost).toHaveBeenCalledWith('/v1/concepts/c1/generate')
  })

  // G2: per-child content controls set on the Profiles page must actually
  // reach the generated brief for the guardian-authored intake flow, not
  // just the profile-linked (child-initiated) path.
  it('shows the selected child excluded themes and folds them into content_nogo', async () => {
    const user = userEvent.setup()
    const withThemes = { ...PROFILE, banned_themes: ['spiders', 'magic'] }
    mockGet.mockReset().mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [withThemes] } })
      if (url === '/v1/generation-jobs') return Promise.resolve({ data: { jobs: [] } })
      throw new Error(`unexpected GET ${url}`)
    })
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/concepts') return Promise.resolve({ data: { concept_id: 'c1' } })
      if (url === '/v1/concepts/c1/generate')
        return Promise.resolve({ data: { job_id: 'j1', status: 'queued' } })
      throw new Error(`unexpected POST ${url}`)
    })
    renderPage()

    expect(
      screen.queryByTestId('intake-excluded-themes')
    ).not.toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: /Reader A/i }))

    expect(screen.getByTestId('intake-excluded-themes')).toHaveTextContent(
      'Excluded for this child: spiders, magic'
    )

    await user.type(screen.getByLabelText(/What's it about/i), 'A quiet walk.')
    await user.click(screen.getByRole('button', { name: /Request Story/i }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/concepts', expect.anything())
    )
    const conceptCall = mockPost.mock.calls.find((c) => c[0] === '/v1/concepts')
    const conceptBody = conceptCall?.[1] as
      | { brief: { content_nogo: string[] } }
      | undefined
    expect(conceptBody?.brief.content_nogo).toEqual(['spiders', 'magic'])
  })

  it('renders each pill state and a failed job error', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [PROFILE] } })
      if (url === '/v1/families/me/budget') return Promise.reject(new Error('no budget mock'))
      return Promise.resolve({
        data: {
          jobs: [
            { id: 'jq', status: 'queued', storybook_status: null, error: null,
              title: 'Q', premise_snippet: 'q', age_band: '8-11', storybook_id: null,
              version: null, created_at: '2026-07-02T00:00:00Z' },
            { id: 'jw', status: 'passed', storybook_status: 'in_review', error: null,
              title: 'W', premise_snippet: 'w', age_band: '8-11', storybook_id: 's1',
              version: 1, created_at: '2026-07-02T00:00:00Z' },
            { id: 'ja', status: 'passed', storybook_status: 'published', error: null,
              title: 'A', premise_snippet: 'a', age_band: '8-11', storybook_id: 's2',
              version: 1, created_at: '2026-07-02T00:00:00Z' },
            { id: 'jf', status: 'failed', storybook_status: null,
              error: 'pipeline blew up', title: 'F', premise_snippet: 'f',
              age_band: '8-11', storybook_id: null, version: null,
              created_at: '2026-07-02T00:00:00Z' },
            { id: 'jn', status: 'needs_review', storybook_status: null,
              error: null, title: 'N', premise_snippet: 'n', age_band: '8-11',
              storybook_id: null, version: null,
              created_at: '2026-07-02T00:00:00Z' },
          ],
        },
      })
    })
    renderPage()

    expect(await screen.findByTestId('request-status-jq')).toHaveTextContent('Generating')
    expect(screen.getByTestId('request-status-jw')).toHaveTextContent('Waiting for review')
    expect(screen.getByTestId('request-status-ja')).toHaveTextContent('Approved')
    expect(screen.getByTestId('request-status-jf')).toHaveTextContent('Failed')
    expect(screen.getByTestId('request-jf')).toHaveTextContent('pipeline blew up')
    // Gate-failed needs_review (no storybook) is Failed, not a phantom
    // review-pending row; with no error field it shows the friendly cause
    // and no technical detail line.
    expect(screen.getByTestId('request-status-jn')).toHaveTextContent('Failed')
    expect(screen.getByTestId('request-jn')).toHaveTextContent('This story could not be made.')
    // The raw report is never fetched or rendered.
    expect(screen.queryByText(/raw-model-output/)).toBeNull()
  })

  it('shows when each request was made, with the absolute time on hover', async () => {
    // Freeze "now" 4 minutes after the job's created_at; the component reads
    // Date.now() once per render, so the age line is deterministic here.
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-07-02T00:04:00Z'))
    mockGet.mockReset().mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [PROFILE] } })
      if (url === '/v1/generation-jobs')
        return Promise.resolve({
          data: {
            jobs: [
              { id: 'jw', status: 'passed', storybook_status: 'in_review', error: null,
                title: 'W', premise_snippet: 'w', age_band: '8-11', storybook_id: 's1',
                version: 1, created_at: '2026-07-02T00:00:00Z' },
            ],
          },
        })
      throw new Error(`unexpected GET ${url}`)
    })
    renderPage()

    const row = await screen.findByTestId('request-jw')
    const age = within(row).getByText('Requested 4 minutes ago')
    // Hover shows the absolute time (locale-formatted from the same ISO input).
    expect(age).toHaveAttribute('title', new Date('2026-07-02T00:00:00Z').toLocaleString())
  })

  it('shows expectation sublines for Generating and Waiting for review rows only', async () => {
    mockGet.mockReset().mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [PROFILE] } })
      if (url === '/v1/generation-jobs')
        return Promise.resolve({
          data: {
            jobs: [
              { id: 'jq', status: 'queued', storybook_status: null, error: null,
                title: 'Q', premise_snippet: 'q', age_band: '8-11', storybook_id: null,
                version: null, created_at: '2026-07-02T00:00:00Z' },
              { id: 'jw', status: 'passed', storybook_status: 'in_review', error: null,
                title: 'W', premise_snippet: 'w', age_band: '8-11', storybook_id: 's1',
                version: 1, created_at: '2026-07-02T00:00:00Z' },
              { id: 'ja', status: 'passed', storybook_status: 'published', error: null,
                title: 'A', premise_snippet: 'a', age_band: '8-11', storybook_id: 's2',
                version: 1, created_at: '2026-07-02T00:00:00Z' },
            ],
          },
        })
      throw new Error(`unexpected GET ${url}`)
    })
    renderPage()

    const genRow = await screen.findByTestId('request-jq')
    expect(genRow).toHaveTextContent('Usually ready in a few minutes.')
    const reviewRow = screen.getByTestId('request-jw')
    expect(reviewRow).toHaveTextContent(
      'A grown-up reviewer checks every story before kids can read it.'
    )
    // The pill itself is unchanged and terminal rows carry no subline.
    expect(within(genRow).getByTestId('request-status-jq')).toHaveTextContent('Generating')
    const approvedRow = screen.getByTestId('request-ja')
    expect(approvedRow).not.toHaveTextContent('Usually ready in a few minutes.')
    expect(approvedRow).not.toHaveTextContent('grown-up reviewer')
  })

  it('shows an inline success notice after a submit and still clears the premise', async () => {
    const user = userEvent.setup()
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/concepts') return Promise.resolve({ data: { concept_id: 'c1' } })
      if (url === '/v1/concepts/c1/generate')
        return Promise.resolve({ data: { job_id: 'j1', status: 'queued' } })
      throw new Error(`unexpected POST ${url}`)
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Reader A/i }))
    await user.type(screen.getByLabelText(/What's it about/i), 'A quiet walk.')
    await user.click(screen.getByRole('button', { name: /Request Story/i }))

    const notice = await screen.findByRole('status')
    expect(notice).toHaveTextContent(
      'Request sent! Your story is being made; watch My Requests below.'
    )
    expect(screen.getByLabelText(/What's it about/i)).toHaveValue('')
  })

  it('shows a friendly failure cause and Try again prefills the form without submitting', async () => {
    const user = userEvent.setup()
    mockGet.mockReset().mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [PROFILE] } })
      if (url === '/v1/generation-jobs')
        return Promise.resolve({
          data: {
            jobs: [
              { id: 'jf', status: 'failed', storybook_status: null,
                error: 'pipeline blew up', title: 'F',
                premise_snippet: 'tide pools and brave crabs', age_band: '8-11',
                storybook_id: null, version: null,
                created_at: '2026-07-02T00:00:00Z' },
            ],
          },
        })
      throw new Error(`unexpected GET ${url}`)
    })
    renderPage()

    const row = await screen.findByTestId('request-jf')
    expect(within(row).getByText('This story could not be made.')).toBeInTheDocument()
    // The technical error stays visible for debugging, demoted to secondary text.
    expect(within(row).getByText('pipeline blew up')).toHaveClass(
      'intake-request__error-detail'
    )

    await user.click(within(row).getByRole('button', { name: /Try again/i }))

    // Prefilled from the job summary: the premise snippet plus the single
    // band-matching child chip; focus lands on the premise for confirmation.
    const premiseField = screen.getByLabelText(/What's it about/i)
    expect(premiseField).toHaveValue('tide pools and brave crabs')
    expect(screen.getByTestId('child-chip-p1')).toHaveAttribute('aria-pressed', 'true')
    expect(premiseField).toHaveFocus()
    // Try again NEVER auto-submits: no concept/generate POST fires.
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('confirms inline after assigning children from the dialog', async () => {
    const user = userEvent.setup()
    mockGet.mockReset().mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [PROFILE] } })
      if (url === '/v1/generation-jobs')
        return Promise.resolve({
          data: {
            jobs: [
              { id: 'ja', status: 'passed', storybook_status: 'published', error: null,
                title: 'A', premise_snippet: 'a', age_band: '8-11', storybook_id: 's2',
                version: 1, created_at: '2026-07-02T00:00:00Z' },
            ],
          },
        })
      if (url === '/v1/storybooks/s2/assignments')
        return Promise.resolve({ data: { storybook_id: 's2', profile_ids: [] } })
      if (url === '/v1/storybooks/s2/content-summary')
        return Promise.resolve({
          data: {
            storybook_id: 's2', version: 1, screened: true, summary: null,
            flagged_count: 0, findings: [],
          },
        })
      throw new Error(`unexpected GET ${url}`)
    })
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/storybooks/s2/assignments')
        return Promise.resolve({ data: { storybook_id: 's2', profile_ids: ['p1'] } })
      throw new Error(`unexpected POST ${url}`)
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Assign more/i }))
    await user.click(await screen.findByRole('checkbox', { name: /Reader A/i }))
    await user.click(screen.getByRole('button', { name: /^Assign$/ }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    // The saved assignment list (the server's full post-save set) confirms inline.
    expect(screen.getByRole('status')).toHaveTextContent('Assigned to 1 child.')
  })

  it('surfaces a load error with a retry when the initial fetch fails', async () => {
    // Both mount fetches reject (e.g. session expiry). Without a surfaced
    // error the page would render a false "no profiles / no requests" state.
    mockGet.mockReset().mockRejectedValue(new Error('boom'))
    renderPage()

    expect(await screen.findByText(/could not load your requests/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument()
    // A failed load must NOT masquerade as a submit failure.
    expect(screen.queryByText(/could not send this request/i)).toBeNull()
  })

  it('guards against a rapid second click firing a duplicate concept POST while saving', async () => {
    // The Request Story button is disabled while `saving` is true (canSubmit
    // includes !saving); a rapid second click on the same render must not slip
    // through and fire a second createConcept + generate pair.
    let resolveGenerate: (() => void) | undefined
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/concepts') return Promise.resolve({ data: { concept_id: 'c1' } })
      if (url === '/v1/concepts/c1/generate')
        return new Promise((resolve) => {
          resolveGenerate = () => resolve({ data: { job_id: 'j1', status: 'queued' } })
        })
      throw new Error(`unexpected POST ${url}`)
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Reader A/i }))
    await user.type(screen.getByLabelText(/What's it about/i), 'A quiet walk.')

    const submitButton = screen.getByRole('button', { name: /Request Story/i })
    fireEvent.click(submitButton)
    fireEvent.click(submitButton)

    expect(mockPost.mock.calls.filter((c) => c[0] === '/v1/concepts')).toHaveLength(1)
    expect(submitButton).toBeDisabled()

    // Let the in-flight generate settle so the test does not leave a dangling
    // promise; the premise field clearing confirms the single submit landed.
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/concepts/c1/generate')
    )
    resolveGenerate?.()
    await waitFor(() =>
      expect(screen.getByLabelText(/What's it about/i)).toHaveValue('')
    )
    expect(mockPost.mock.calls.filter((c) => c[0] === '/v1/concepts')).toHaveLength(1)
  })

  it('shows a submit error when creating the concept fails', async () => {
    const user = userEvent.setup()
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/concepts') return Promise.reject(new Error('nope'))
      throw new Error(`unexpected POST ${url}`)
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Reader A/i }))
    await user.type(screen.getByLabelText(/What's it about/i), 'A quiet walk.')
    await user.click(screen.getByRole('button', { name: /Request Story/i }))

    expect(await screen.findByText(/could not send this request/i)).toBeInTheDocument()
    // generate must never be attempted once createConcept fails.
    expect(mockPost).not.toHaveBeenCalledWith('/v1/concepts/c1/generate')
  })

  it('does not report a submit failure when only the post-submit refresh fails', async () => {
    // The concept + job POSTs succeed (durable); only the trailing job-list
    // refresh rejects. This must surface as a load error, NOT a submit failure,
    // so the guardian is not prompted to retry an already-succeeded request
    // (which would create a duplicate concept + generation job).
    const user = userEvent.setup()
    let jobsCalls = 0
    mockGet.mockReset().mockImplementation((url: string) => {
      if (url === '/v1/profiles')
        return Promise.resolve({ data: { profiles: [PROFILE] } })
      if (url === '/v1/generation-jobs') {
        jobsCalls += 1
        // First call is the initial load (succeeds); the post-submit refresh rejects.
        return jobsCalls === 1
          ? Promise.resolve({ data: { jobs: [] } })
          : Promise.reject(new Error('refresh boom'))
      }
      throw new Error(`unexpected GET ${url}`)
    })
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/concepts') return Promise.resolve({ data: { concept_id: 'c1' } })
      if (url === '/v1/concepts/c1/generate')
        return Promise.resolve({ data: { job_id: 'j1', status: 'queued' } })
      throw new Error(`unexpected POST ${url}`)
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Reader A/i }))
    await user.type(screen.getByLabelText(/What's it about/i), 'A quiet walk.')
    await user.click(screen.getByRole('button', { name: /Request Story/i }))

    // The refresh failure surfaces as a load error, not a submit failure.
    expect(await screen.findByText(/could not load your requests/i)).toBeInTheDocument()
    expect(screen.queryByText(/could not send this request/i)).toBeNull()
    // The concept was created exactly once (no duplicate from a false retry prompt).
    expect(mockPost.mock.calls.filter((c) => c[0] === '/v1/concepts')).toHaveLength(1)
  })

  it('retries the load when the Retry button is clicked after a load failure', async () => {
    const user = userEvent.setup()
    let calls = 0
    mockGet.mockReset().mockImplementation((url: string) => {
      // BudgetBanner's own mount fetch is routed out of the `calls` counter
      // (same reasoning as the polling test above): it is a sibling fetch,
      // not one of the two "mount fetches" this counter tracks.
      if (url === '/v1/families/me/budget') return Promise.reject(new Error('no budget mock'))
      calls += 1
      // Both mount fetches (profiles + jobs) fail; the first retry succeeds.
      if (calls <= 2) return Promise.reject(new Error('boom'))
      return Promise.resolve(getMock(url))
    })
    renderPage()

    await screen.findByText(/could not load your requests/i)
    await user.click(screen.getByRole('button', { name: /Retry/i }))

    await waitFor(() =>
      expect(screen.queryByText(/could not load your requests/i)).not.toBeInTheDocument()
    )
    expect(await screen.findByRole('button', { name: /Reader A/i })).toBeInTheDocument()
  })

  it('opens the assign dialog from an Approved row and closes it', async () => {
    const user = userEvent.setup()
    mockGet.mockReset().mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [PROFILE] } })
      if (url === '/v1/generation-jobs') {
        return Promise.resolve({
          data: {
            jobs: [
              {
                id: 'ja', status: 'passed', storybook_status: 'published', error: null,
                title: 'A', premise_snippet: 'a', age_band: '8-11', storybook_id: 's2',
                version: 1, created_at: '2026-07-02T00:00:00Z',
              },
            ],
          },
        })
      }
      if (url === '/v1/storybooks/s2/assignments')
        return Promise.resolve({ data: { storybook_id: 's2', profile_ids: [] } })
      if (url === '/v1/storybooks/s2/content-summary')
        return Promise.resolve({
          data: {
            storybook_id: 's2', version: 1, screened: true, summary: null,
            flagged_count: 0, findings: [],
          },
        })
      throw new Error(`unexpected GET ${url}`)
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Assign more/i }))
    const dialog = await screen.findByRole('dialog', { name: /Assign to children/i })
    expect(dialog).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Cancel$/i }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('polls while a job is active and stops after it settles', async () => {
    // Deviation from the brief: Testing Library's fake-timer detection only
    // fires when a `jest` global exists (jestFakeTimersAreEnabled in
    // @testing-library/dom), so under Vitest `findBy`/`waitFor` cannot advance
    // the faked timers and hang. Drive the flushes explicitly with act +
    // advanceTimersByTimeAsync instead; the assertions and intent are identical.
    vi.useFakeTimers()
    const active = {
      id: 'jq', status: 'queued', storybook_status: null, error: null, title: 'Q',
      premise_snippet: 'q', age_band: '8-11', storybook_id: null, version: null,
      created_at: '2026-07-02T00:00:00Z',
    }
    const settled = { ...active, status: 'passed', storybook_status: 'in_review' }
    let call = 0
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [PROFILE] } })
      // BudgetBanner also fires a GET on mount (a sibling of the jobs poll,
      // not the jobs endpoint itself); matching it explicitly and routing
      // it away from the `call` counter keeps that counter meaning exactly
      // "how many times the jobs list has been fetched", which the
      // call === 1 ? active : settled branch below depends on.
      if (url === '/v1/families/me/budget') return Promise.reject(new Error('no budget mock'))
      call += 1
      return Promise.resolve({ data: { jobs: [call === 1 ? active : settled] } })
    })
    renderPage()

    // Flush the initial load (promise-only, no timers): shows the active pill.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByTestId('request-status-jq')).toHaveTextContent('Generating')

    // One poll interval fires: the refetch returns the settled job.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000)
    })
    expect(screen.getByTestId('request-status-jq')).toHaveTextContent('Waiting for review')

    // The job has settled, so the interval is cleared: further time does not poll.
    const callsAfterSettle = call
    await act(async () => {
      await vi.advanceTimersByTimeAsync(24000)
    })
    expect(call).toBe(callsAfterSettle)
  })
})

describe('IntakePage G13 balance banner and ADR-015 G7 budget surfacing', () => {
  function mockLoadAndBudget(budget: unknown) {
    mockGet.mockReset().mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [PROFILE] } })
      if (url === '/v1/generation-jobs') return Promise.resolve({ data: { jobs: [] } })
      if (url === '/v1/families/me/budget') return Promise.resolve({ data: budget })
      throw new Error(`unexpected GET ${url}`)
    })
  }

  it('shows the balance banner near the submit button', async () => {
    mockLoadAndBudget({ quota: 5, spent_this_month: 2, remaining: 3, children: [] })
    renderPage()
    expect(await screen.findByTestId('budget-banner')).toHaveTextContent(
      '3 of 5 stories left this month'
    )
  })

  it('dispatches the story-requests-changed event after a successful submit (banner refresh signal)', async () => {
    const user = userEvent.setup()
    mockLoadAndBudget({ quota: 5, spent_this_month: 2, remaining: 3, children: [] })
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/concepts') return Promise.resolve({ data: { concept_id: 'c1' } })
      if (url === '/v1/concepts/c1/generate')
        return Promise.resolve({ data: { job_id: 'j1', status: 'queued' } })
      throw new Error(`unexpected POST ${url}`)
    })
    const listener = vi.fn()
    window.addEventListener(STORY_REQUESTS_CHANGED_EVENT, listener)
    try {
      renderPage()
      await user.click(await screen.findByRole('button', { name: /Reader A/i }))
      await user.type(screen.getByLabelText(/What's it about/i), 'A quiet walk.')
      await user.click(screen.getByRole('button', { name: /Request Story/i }))

      await waitFor(() => expect(listener).toHaveBeenCalledTimes(1))
    } finally {
      window.removeEventListener(STORY_REQUESTS_CHANGED_EVENT, listener)
    }
  })

  it('surfaces the friendly budget message on a budget-exhausted submit', async () => {
    // #ASSUME (IntakePage.tsx submit()): this path is not reachable against
    // the live backend today (neither /v1/concepts nor its /generate
    // enforces the family quota yet), but the handling stays correct and
    // harmless either way, so it is worth pinning.
    const user = userEvent.setup()
    mockLoadAndBudget({ quota: 5, spent_this_month: 5, remaining: 0, children: [] })
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/concepts')
        return Promise.reject(
          Object.assign(new Error('monthly story budget reached'), {
            isAxiosError: true,
            response: { status: 409, data: { message: 'monthly story budget reached' } },
          })
        )
      throw new Error(`unexpected POST ${url}`)
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Reader A/i }))
    await user.type(screen.getByLabelText(/What's it about/i), 'A quiet walk.')
    await user.click(screen.getByRole('button', { name: /Request Story/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/used this month's story budget/i)
    expect(alert).toHaveTextContent(/next month/i)
    expect(alert).not.toHaveTextContent(/could not send this request/i)
  })

  it('keeps the generic transient message for a non-budget submit failure', async () => {
    const user = userEvent.setup()
    mockLoadAndBudget({ quota: 5, spent_this_month: 0, remaining: 5, children: [] })
    mockPost.mockImplementation((url: string) => {
      if (url === '/v1/concepts') return Promise.reject(new Error('nope'))
      throw new Error(`unexpected POST ${url}`)
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Reader A/i }))
    await user.type(screen.getByLabelText(/What's it about/i), 'A quiet walk.')
    await user.click(screen.getByRole('button', { name: /Request Story/i }))

    expect(await screen.findByText(/could not send this request/i)).toBeInTheDocument()
  })
})
