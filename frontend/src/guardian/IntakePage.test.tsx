import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { IntakePage } from './IntakePage'

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

  it('renders each pill state and a failed job error', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: [PROFILE] } })
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
    // review-pending row; with no error field only the friendly pill shows.
    expect(screen.getByTestId('request-status-jn')).toHaveTextContent('Failed')
    // The raw report is never fetched or rendered.
    expect(screen.queryByText(/raw-model-output/)).toBeNull()
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
