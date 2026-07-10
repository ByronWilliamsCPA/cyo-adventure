import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RequestsPage } from './RequestsPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

// This page's queue is admin-only (a plain guardian gets 403, see the
// forbidden-notice test below), so the existing queue-review cases run as the
// admin principal by default; that also gates the guardian-only
// RequestStoryForm embed (WS-B PR2) out of every pre-existing test, matching
// its own isolated coverage in RequestStoryForm.test.tsx.
const mockUseAuth = vi.fn()
vi.mock('../auth/useAuth', () => ({
  useAuth: (): unknown => mockUseAuth(),
}))

function principal(role: 'guardian' | 'admin') {
  return { principal: { subject: 's', role, familyId: 'f', profileIds: [] } }
}

const PENDING_URL = '/v1/story-requests?status=pending'

const DRAGON_REQUEST = {
  id: 'req-1',
  profile_id: 'prof-1',
  status: 'pending',
  request_text: 'A story about a friendly dragon',
  moderation_flags: [],
  created_at: '2026-07-04T10:00:00Z',
  initiator_role: 'child',
  age_band: '8-11',
  length: null,
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null,
}

const FLAGGED_REQUEST = {
  id: 'req-2',
  profile_id: 'prof-2',
  status: 'pending',
  request_text: 'A pirate adventure',
  moderation_flags: [{ category: 'violence', verdict: 'flag', message: 'Mild peril' }],
  created_at: '2026-07-04T10:05:00Z',
  initiator_role: 'child',
  age_band: '8-11',
  length: null,
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null,
}

const BLOCKED_REQUEST = {
  id: 'req-3',
  profile_id: 'prof-3',
  status: 'blocked',
  request_text: null,
  moderation_flags: [{ category: 'unsafe', verdict: 'block', message: 'Hard block' }],
  created_at: '2026-07-04T10:10:00Z',
  initiator_role: 'child',
  age_band: '8-11',
  length: null,
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null,
}

function mockPending(requests: unknown[]) {
  mockGet.mockImplementation((url: string) =>
    url === PENDING_URL
      ? Promise.resolve({ data: { requests } })
      : Promise.reject(new Error(`unexpected GET ${url}`))
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPending([DRAGON_REQUEST])
  mockUseAuth.mockReset()
  mockUseAuth.mockReturnValue(principal('admin'))
})

describe('RequestsPage', () => {
  it('renders pending rows with their request text', async () => {
    mockPending([DRAGON_REQUEST, FLAGGED_REQUEST])
    render(<RequestsPage />)
    expect(await screen.findByText('A story about a friendly dragon')).toBeInTheDocument()
    expect(screen.getByText('A pirate adventure')).toBeInTheDocument()
    expect(screen.getByText('violence')).toBeInTheDocument()
  })

  it('shows a redacted note for a blocked row with no request text', async () => {
    mockPending([BLOCKED_REQUEST])
    render(<RequestsPage />)
    expect(await screen.findByText('Idea hidden by content check')).toBeInTheDocument()
    expect(screen.getByText('unsafe')).toBeInTheDocument()
  })

  it('approve calls the adapter and optimistically removes the row', async () => {
    mockPost.mockResolvedValue({
      data: { id: 'req-1', status: 'approved', concept_id: 'concept-1', job_id: 'job-1' },
    })
    render(<RequestsPage />)
    const title = await screen.findByText('A story about a friendly dragon')
    fireEvent.change(screen.getByLabelText('Story length'), {
      target: { value: 'medium' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/req-1/approve', {
        age_band: '8-11',
        length: 'medium',
        narrative_style: 'prose',
      })
    )
    await waitFor(() => expect(title).not.toBeInTheDocument())
  })

  it('approve is disabled until a length is chosen, then sends the confirmation body', async () => {
    mockPost.mockResolvedValue({
      data: { id: 'req-1', status: 'approved', concept_id: 'concept-1' },
    })
    render(<RequestsPage />)
    await screen.findByText('A story about a friendly dragon')
    const approveButton = screen.getByRole('button', { name: 'Approve' })
    expect(approveButton).toBeDisabled()
    expect(screen.queryByLabelText('Story style')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Story length'), {
      target: { value: 'medium' },
    })
    expect(approveButton).toBeEnabled()
    fireEvent.click(approveButton)
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/req-1/approve', {
        age_band: '8-11',
        length: 'medium',
        narrative_style: 'prose',
      })
    )
  })

  it('style select renders only for teen bands', async () => {
    mockPending([{ ...DRAGON_REQUEST, age_band: '13-16' }])
    render(<RequestsPage />)
    await screen.findByText('A story about a friendly dragon')
    expect(screen.getByLabelText('Story style')).toBeInTheDocument()
  })

  it('changing the age band select updates the row and hides the style select when leaving a teen band', async () => {
    const user = userEvent.setup()
    mockPending([{ ...DRAGON_REQUEST, age_band: '13-16' }])
    render(<RequestsPage />)
    await screen.findByText('A story about a friendly dragon')
    expect(screen.getByLabelText('Story style')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Age band'), '8-11')

    expect(screen.getByLabelText<HTMLSelectElement>('Age band').value).toBe('8-11')
    // Switching away from a teen band clears the stale gamebook selection and
    // hides the now-irrelevant style select.
    expect(screen.queryByLabelText('Story style')).not.toBeInTheDocument()
  })

  it('changing the story style select updates the row and is included in the approve body', async () => {
    const user = userEvent.setup()
    mockPending([{ ...DRAGON_REQUEST, age_band: '13-16' }])
    mockPost.mockResolvedValue({
      data: { id: 'req-1', status: 'approved', concept_id: 'concept-1', job_id: 'job-1' },
    })
    render(<RequestsPage />)
    await screen.findByText('A story about a friendly dragon')

    await user.selectOptions(screen.getByLabelText('Story style'), 'gamebook')
    expect(screen.getByLabelText<HTMLSelectElement>('Story style').value).toBe('gamebook')

    await user.selectOptions(screen.getByLabelText('Story length'), 'medium')
    await user.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/req-1/approve', {
        age_band: '13-16',
        length: 'medium',
        narrative_style: 'gamebook',
      })
    )
  })

  it('prefills the series input from proposed_series_title and includes it in the approve body', async () => {
    mockPending([{ ...DRAGON_REQUEST, proposed_series_title: 'Fox Tales' }])
    mockPost.mockResolvedValue({
      data: { id: 'req-1', status: 'approved', concept_id: 'concept-1', job_id: 'job-1' },
    })
    render(<RequestsPage />)
    await screen.findByText('A story about a friendly dragon')
    const seriesInput = screen.getByLabelText<HTMLInputElement>('Series title (optional)')
    expect(seriesInput.value).toBe('Fox Tales')
    fireEvent.change(screen.getByLabelText('Story length'), {
      target: { value: 'medium' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/req-1/approve', {
        age_band: '8-11',
        length: 'medium',
        narrative_style: 'prose',
        series_title: 'Fox Tales',
      })
    )
  })

  it('sends a body without series_title when the prefilled series input is cleared', async () => {
    mockPending([{ ...DRAGON_REQUEST, proposed_series_title: 'Fox Tales' }])
    mockPost.mockResolvedValue({
      data: { id: 'req-1', status: 'approved', concept_id: 'concept-1', job_id: 'job-1' },
    })
    render(<RequestsPage />)
    await screen.findByText('A story about a friendly dragon')
    fireEvent.change(screen.getByLabelText('Series title (optional)'), {
      target: { value: '' },
    })
    fireEvent.change(screen.getByLabelText('Story length'), {
      target: { value: 'medium' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/req-1/approve', {
        age_band: '8-11',
        length: 'medium',
        narrative_style: 'prose',
      })
    )
  })

  it('shows a continuation note and disables the band select for an anchored row', async () => {
    mockPending([{ ...DRAGON_REQUEST, anchor_storybook_id: 's_1' }])
    render(<RequestsPage />)
    await screen.findByText('A story about a friendly dragon')
    expect(screen.getByText('Continues an existing series')).toBeInTheDocument()
    expect(screen.queryByLabelText('Series title (optional)')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Age band')).toBeDisabled()
  })

  it('decline calls the adapter and removes the row', async () => {
    mockPost.mockResolvedValue({ data: { id: 'req-1', status: 'declined' } })
    render(<RequestsPage />)
    const title = await screen.findByText('A story about a friendly dragon')
    fireEvent.click(screen.getByRole('button', { name: 'Decline' }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/req-1/decline'))
    await waitFor(() => expect(title).not.toBeInTheDocument())
  })

  it('shows the safety-reviewer notice on a 403 (plain guardian token)', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    render(<RequestsPage />)
    expect(await screen.findByText(/safety reviewer/i)).toBeInTheDocument()
  })

  it('shows a generic error when the queue fails for another reason', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    render(<RequestsPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })

  it('shows the empty state when there are no pending requests', async () => {
    mockPending([])
    render(<RequestsPage />)
    expect(await screen.findByText(/No requests to review/i)).toBeInTheDocument()
  })

  it('double-clicking Approve results in exactly one adapter call', async () => {
    let resolvePost: (value: { data: unknown }) => void = () => {}
    mockPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePost = resolve
        })
    )
    render(<RequestsPage />)
    await screen.findByText('A story about a friendly dragon')
    fireEvent.change(screen.getByLabelText('Story length'), {
      target: { value: 'medium' },
    })
    const approveButton = screen.getByRole('button', { name: 'Approve' })
    fireEvent.click(approveButton)
    fireEvent.click(approveButton)
    expect(mockPost).toHaveBeenCalledTimes(1)
    resolvePost({
      data: { id: 'req-1', status: 'approved', concept_id: 'concept-1', job_id: 'job-1' },
    })
    await waitFor(() => expect(approveButton).not.toBeInTheDocument())
  })

  it('both buttons in a row are disabled while an action is in flight', async () => {
    let resolvePost: (value: { data: unknown }) => void = () => {}
    mockPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePost = resolve
        })
    )
    render(<RequestsPage />)
    await screen.findByText('A story about a friendly dragon')
    fireEvent.change(screen.getByLabelText('Story length'), {
      target: { value: 'medium' },
    })
    const approveButton = screen.getByRole('button', { name: 'Approve' })
    const declineButton = screen.getByRole('button', { name: 'Decline' })
    fireEvent.click(approveButton)
    await waitFor(() => expect(approveButton).toBeDisabled())
    expect(declineButton).toBeDisabled()
    resolvePost({
      data: { id: 'req-1', status: 'approved', concept_id: 'concept-1', job_id: 'job-1' },
    })
    await waitFor(() => expect(approveButton).not.toBeInTheDocument())
  })

  it('shows a visible alert and keeps the row when approve is rejected', async () => {
    mockPost.mockRejectedValueOnce(new Error('boom'))
    render(<RequestsPage />)
    const title = await screen.findByText('A story about a friendly dragon')
    fireEvent.change(screen.getByLabelText('Story length'), {
      target: { value: 'medium' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not update/i)
    expect(title).toBeInTheDocument()
    const approveButton = screen.getByRole('button', { name: 'Approve' })
    expect(approveButton).not.toBeDisabled()
  })

  it('renders the guardian request-a-story form above the queue for a guardian principal', async () => {
    mockUseAuth.mockReturnValue(principal('guardian'))
    mockGet.mockImplementation((url: string) =>
      url === PENDING_URL
        ? Promise.resolve({ data: { requests: [] } })
        : url === '/v1/profiles'
          ? Promise.resolve({ data: { profiles: [] } })
          : Promise.reject(new Error(`unexpected GET ${url}`))
    )
    render(<RequestsPage />)
    expect(await screen.findByLabelText(/what should the story be about/i)).toBeInTheDocument()
  })

  it('does not render the request-a-story form for an admin principal', async () => {
    render(<RequestsPage />)
    await screen.findByText('A story about a friendly dragon')
    expect(screen.queryByLabelText(/what should the story be about/i)).not.toBeInTheDocument()
  })
})
