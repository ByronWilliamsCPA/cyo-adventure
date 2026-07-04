import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RequestsPage } from './RequestsPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const PENDING_URL = '/v1/story-requests?status=pending'

const DRAGON_REQUEST = {
  id: 'req-1',
  profile_id: 'prof-1',
  status: 'pending',
  request_text: 'A story about a friendly dragon',
  moderation_flags: [],
  created_at: '2026-07-04T10:00:00Z',
}

const FLAGGED_REQUEST = {
  id: 'req-2',
  profile_id: 'prof-2',
  status: 'pending',
  request_text: 'A pirate adventure',
  moderation_flags: [{ category: 'violence', verdict: 'flag', message: 'Mild peril' }],
  created_at: '2026-07-04T10:05:00Z',
}

const BLOCKED_REQUEST = {
  id: 'req-3',
  profile_id: 'prof-3',
  status: 'blocked',
  request_text: null,
  moderation_flags: [{ category: 'unsafe', verdict: 'block', message: 'Hard block' }],
  created_at: '2026-07-04T10:10:00Z',
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
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/req-1/approve')
    )
    await waitFor(() => expect(title).not.toBeInTheDocument())
  })

  it('decline calls the adapter and removes the row', async () => {
    mockPost.mockResolvedValue({ data: null })
    render(<RequestsPage />)
    const title = await screen.findByText('A story about a friendly dragon')
    fireEvent.click(screen.getByRole('button', { name: 'Decline' }))
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/req-1/decline')
    )
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
})
