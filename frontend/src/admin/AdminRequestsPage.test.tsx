import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminRequestsPage } from './AdminRequestsPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const REQUEST = {
  id: 'r1',
  profile_id: null,
  status: 'pending',
  request_text: 'a dragon who bakes bread',
  moderation_flags: [],
  created_at: '2026-07-12T00:00:00Z',
  initiator_role: 'child',
  age_band: '8-11',
  length: null,
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null,
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockGet.mockImplementation((url: string) =>
    url.startsWith('/v1/admin/story-requests')
      ? Promise.resolve({ data: { requests: [REQUEST] } })
      : url === '/v1/admin/families'
        ? Promise.resolve({ data: { families: [{ id: 'fam-1', name: 'The Ambers' }] } })
        : Promise.reject(new Error(`unexpected GET ${url}`))
  )
})

describe('AdminRequestsPage', () => {
  it('reads the cross-family queue from the admin surface, not the guardian list', async () => {
    render(
      <MemoryRouter>
        <AdminRequestsPage />
      </MemoryRouter>
    )
    expect(await screen.findByText('a dragon who bakes bread')).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith('/v1/admin/story-requests?status=pending')
    const urls = mockGet.mock.calls.map((call) => String(call[0]))
    expect(urls).not.toContain('/v1/story-requests?status=pending')
  })

  it('renders the admin-mode request form with its family selector', async () => {
    render(
      <MemoryRouter>
        <AdminRequestsPage />
      </MemoryRouter>
    )
    expect(await screen.findByLabelText(/what should the story be about/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/family/i)).toBeInTheDocument()
  })
})
