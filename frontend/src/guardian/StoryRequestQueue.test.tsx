import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../notifications/ToastProvider'
import { StoryRequestQueue } from './StoryRequestQueue'

/**
 * Dedicated unit coverage for StoryRequestQueue, the shared screening/
 * anchoring review component embedded by both RequestsPage (scope='family')
 * and AdminRequestsPage (scope='all'). Those two page-level test files cover
 * scope selection, role-based access, and a couple of incidental cases, but
 * neither exercises this component's own branching logic in isolation. This
 * file closes that gap: the anchored-series row state (disabled band select,
 * hidden series-title input, continuation note), the teen-only narrative
 * style field, and the approve payload's series_title trimming.
 */
const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const FAMILY_URL = '/v1/story-requests?status=pending'

const BASE_REQUEST = {
  id: 'req-1',
  profile_id: 'prof-1',
  status: 'pending' as const,
  request_text: 'A story about a friendly dragon',
  moderation_flags: [],
  created_at: '2026-07-04T10:00:00Z',
  initiator_role: 'child' as const,
  age_band: '8-11',
  length: null,
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null as string | null,
}

function mockPending(requests: unknown[]) {
  mockGet.mockImplementation((url: string) =>
    url === FAMILY_URL
      ? Promise.resolve({ data: { requests } })
      : Promise.reject(new Error(`unexpected GET ${url}`))
  )
}

// ToastProvider wraps every render, mirroring App.tsx's production mounting:
// StoryRequestQueue calls useToast() unconditionally, so a bare render would
// throw its outside-provider error (same pattern as RequestsPage.test.tsx).
function renderQueue() {
  return render(
    <ToastProvider>
      <StoryRequestQueue scope="family" />
    </ToastProvider>
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPending([BASE_REQUEST])
})

describe('StoryRequestQueue anchoring', () => {
  it('shows the series-title input and no continuation note for a non-anchored row', async () => {
    renderQueue()
    await screen.findByText('A story about a friendly dragon')

    expect(screen.getByLabelText('Series title (optional)')).toBeEnabled()
    expect(screen.getByLabelText('Age band')).not.toBeDisabled()
    expect(screen.queryByText('Continues an existing series')).not.toBeInTheDocument()
  })

  it('disables the age band select and shows a continuation note for an anchored row', async () => {
    mockPending([{ ...BASE_REQUEST, anchor_storybook_id: 'sb_1' }])
    renderQueue()
    await screen.findByText('A story about a friendly dragon')

    const ageBand = screen.getByLabelText('Age band')
    expect(ageBand).toBeDisabled()
    expect(ageBand).toHaveAttribute('aria-describedby', `series-note-${BASE_REQUEST.id}`)
    expect(screen.getByText('Continues an existing series')).toHaveAttribute(
      'id',
      `series-note-${BASE_REQUEST.id}`
    )
    expect(screen.queryByLabelText('Series title (optional)')).not.toBeInTheDocument()
  })

  it('omits series_title from the approve payload when left blank', async () => {
    mockPost.mockResolvedValue({ data: { id: BASE_REQUEST.id, status: 'approved' } })
    const user = userEvent.setup()
    renderQueue()
    await screen.findByText('A story about a friendly dragon')

    await user.selectOptions(screen.getByLabelText('Story length'), 'short')
    await user.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const [, body] = mockPost.mock.calls[0] as [string, Record<string, unknown>]
    expect(body).not.toHaveProperty('series_title')
  })

  it('trims and includes series_title in the approve payload when provided', async () => {
    mockPost.mockResolvedValue({ data: { id: BASE_REQUEST.id, status: 'approved' } })
    const user = userEvent.setup()
    renderQueue()
    await screen.findByText('A story about a friendly dragon')

    await user.type(screen.getByLabelText('Series title (optional)'), '  The Dragon Chronicles  ')
    await user.selectOptions(screen.getByLabelText('Story length'), 'short')
    await user.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const [, body] = mockPost.mock.calls[0] as [string, Record<string, unknown>]
    expect(body.series_title).toBe('The Dragon Chronicles')
  })
})

describe('StoryRequestQueue teen narrative style', () => {
  it('hides the story style field for a non-teen age band', async () => {
    renderQueue()
    await screen.findByText('A story about a friendly dragon')
    expect(screen.queryByLabelText('Story style')).not.toBeInTheDocument()
  })

  it('shows the story style field once a teen age band is selected', async () => {
    const user = userEvent.setup()
    renderQueue()
    await screen.findByText('A story about a friendly dragon')

    await user.selectOptions(screen.getByLabelText('Age band'), '13-16')
    expect(screen.getByLabelText('Story style')).toBeInTheDocument()
  })

  it('resets narrative style to prose when the age band moves back out of the teen bands', async () => {
    mockPost.mockResolvedValue({ data: { id: BASE_REQUEST.id, status: 'approved' } })
    const user = userEvent.setup()
    renderQueue()
    await screen.findByText('A story about a friendly dragon')

    await user.selectOptions(screen.getByLabelText('Age band'), '13-16')
    await user.selectOptions(screen.getByLabelText('Story style'), 'gamebook')
    await user.selectOptions(screen.getByLabelText('Age band'), '8-11')
    expect(screen.queryByLabelText('Story style')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Story length'), 'short')
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const [, body] = mockPost.mock.calls[0] as [string, Record<string, unknown>]
    expect(body.narrative_style).toBe('prose')
  })
})

describe('StoryRequestQueue moderation flags and blocked text', () => {
  it('renders every moderation flag as a badge', async () => {
    mockPending([
      {
        ...BASE_REQUEST,
        moderation_flags: [
          { category: 'violence', verdict: 'flag', message: 'Mild peril' },
          { category: 'language', verdict: 'flag', message: 'Mild language' },
        ],
      },
    ])
    renderQueue()
    await screen.findByText('A story about a friendly dragon')
    expect(screen.getByText('violence')).toBeInTheDocument()
    expect(screen.getByText('language')).toBeInTheDocument()
  })

  it('falls back to a placeholder when request_text is null', async () => {
    mockPending([{ ...BASE_REQUEST, request_text: null, status: 'blocked' }])
    renderQueue()
    expect(await screen.findByText('Idea hidden by content check')).toBeInTheDocument()
  })
})
