import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthoringQueuePage } from './AuthoringQueuePage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const APPROVED_REQUEST = {
  id: 'req-1',
  profile_id: 'p1',
  status: 'approved',
  request_text: 'A story about a friendly dragon',
  moderation_flags: [],
  created_at: '2026-07-04T10:00:00Z',
  initiator_role: 'child',
  age_band: '8-11',
  length: 'short',
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null,
}

const ALLOWLIST = {
  rows: [
    { id: 'a1', provider: 'anthropic', model_id: 'claude-sonnet-4-6', enabled: true, display_name: 'Sonnet' },
  ],
}

function mockGetByPath() {
  mockGet.mockImplementation((path: string) => {
    if (path === '/v1/admin/provider-allowlist') return Promise.resolve({ data: ALLOWLIST })
    return Promise.resolve({ data: { requests: [APPROVED_REQUEST] } })
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockGetByPath()
})

describe('AuthoringQueuePage', () => {
  it('lists approved requests awaiting an authoring plan', async () => {
    render(<AuthoringQueuePage />)
    expect(await screen.findByText('A story about a friendly dragon')).toBeInTheDocument()
    expect(screen.getByText('8-11 · short · prose')).toBeInTheDocument()
  })

  it('shows the empty state when nothing is approved yet', async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === '/v1/admin/provider-allowlist') return Promise.resolve({ data: ALLOWLIST })
      return Promise.resolve({ data: { requests: [] } })
    })
    render(<AuthoringQueuePage />)
    expect(
      await screen.findByText('No approved requests are waiting for an authoring plan.')
    ).toBeInTheDocument()
  })

  it('opens the authoring plan dialog and removes the row on success', async () => {
    mockPost.mockResolvedValue({
      data: {
        request_id: 'req-1',
        concept_id: 'c1',
        job_id: 'job-1',
        method: 'skeleton_fill',
        mechanism: 'skill',
        status: 'queued',
        skeleton_alternatives: [],
        warnings: [],
      },
    })
    const user = userEvent.setup()
    render(<AuthoringQueuePage />)
    await screen.findByText('A story about a friendly dragon')

    await user.click(screen.getByRole('button', { name: 'Build authoring plan' }))
    expect(screen.getByRole('dialog')).toBeVisible()

    // Skill mechanism is the default, and its prep model defaults to the
    // first recognized Claude Code session model; no input is required.
    await user.click(screen.getByRole('button', { name: 'Create plan' }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests/req-1/authoring-plan', {
        method: 'skeleton_fill',
        mechanism: 'skill',
        prep_model: 'sonnet',
      })
    )
    await waitFor(() =>
      expect(screen.queryByText('A story about a friendly dragon')).not.toBeInTheDocument()
    )
  })

  it('shows a generic error alert when loading the queue throws an Error', async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === '/v1/admin/provider-allowlist') return Promise.resolve({ data: ALLOWLIST })
      return Promise.reject(new Error('network down'))
    })
    render(<AuthoringQueuePage />)
    expect(
      await screen.findByText('We could not load the authoring queue. Please reload.')
    ).toBeInTheDocument()
  })

  it('shows a generic error alert when the queue rejects with a non-Error value', async () => {
    // #EDGE: data-integrity: a thrown value need not be an Error instance (a
    // rejected promise can carry any value); the `err instanceof Error`
    // branch in the load catch handler must not throw either way.
    // #VERIFY: covered here by rejecting with a plain string.
    mockGet.mockImplementation((path: string) => {
      if (path === '/v1/admin/provider-allowlist') return Promise.resolve({ data: ALLOWLIST })
      // Intentionally a non-Error rejection reason to exercise the
      // `err instanceof Error` false branch below.
      // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
      return Promise.reject('boom')
    })
    render(<AuthoringQueuePage />)
    expect(
      await screen.findByText('We could not load the authoring queue. Please reload.')
    ).toBeInTheDocument()
  })

  it('falls back to placeholder text when request_text and length are absent', async () => {
    mockGet.mockImplementation((path: string) => {
      if (path === '/v1/admin/provider-allowlist') return Promise.resolve({ data: ALLOWLIST })
      return Promise.resolve({
        data: { requests: [{ ...APPROVED_REQUEST, request_text: null, length: null }] },
      })
    })
    render(<AuthoringQueuePage />)
    expect(await screen.findByText('Untitled request')).toBeInTheDocument()
    expect(screen.getByText('8-11 · length not set · prose')).toBeInTheDocument()
  })
})
