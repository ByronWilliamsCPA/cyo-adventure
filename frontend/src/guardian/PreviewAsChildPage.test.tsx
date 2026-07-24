import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PreviewAsChildPage } from './PreviewAsChildPage'

const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const PROFILES = [
  {
    id: 'p1',
    display_name: 'Mia',
    age_band: '5-8',
    reading_level_cap: 99,
    avatar: 'fox',
    tts_enabled: false,
    reduce_motion: true,
    created_at: '2026-07-02T00:00:00Z',
  },
]

function renderPreview(profileId = 'p1') {
  return render(
    <MemoryRouter initialEntries={[`/guardian/preview/${profileId}`]}>
      <Routes>
        <Route path="/guardian/preview/:profileId" element={<PreviewAsChildPage />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset().mockImplementation((url: string) => {
    if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: PROFILES } })
    if (url === '/v1/library') return Promise.resolve({ data: { stories: [] } })
    return Promise.resolve({ data: {} })
  })
})

describe('PreviewAsChildPage', () => {
  it('shows a read-only banner naming the previewed child, with an exit link', async () => {
    renderPreview()
    expect(await screen.findByText('Previewing as Mia (read-only)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /exit preview/i })).toHaveAttribute(
      'href',
      '/guardian/profiles'
    )
  })

  it('sets data-age-band and data-reduce-motion from the previewed profile', async () => {
    const { container } = renderPreview()
    await screen.findByText('Previewing as Mia (read-only)')
    const root = container.querySelector('.preview-as-child')
    expect(root).toHaveAttribute('data-age-band', '5-8')
    expect(root).toHaveAttribute('data-reduce-motion', 'true')
  })

  it('renders LibraryPage underneath in read-only mode (no rating group)', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.resolve({ data: { profiles: PROFILES } })
      if (url === '/v1/library') {
        return Promise.resolve({
          data: {
            stories: [
              {
                id: 's1',
                title: 'The Lantern',
                version: 1,
                age_band: '5-8',
                tier: 1,
                reading_level_target: 2,
                node_count: 5,
                rating: null,
                progress: null,
                series_id: null,
                book_index: null,
                cover_url: null,
              },
            ],
          },
        })
      }
      return Promise.resolve({ data: {} })
    })
    const { container } = renderPreview()
    expect(await screen.findByText('The Lantern')).toBeInTheDocument()
    expect(screen.queryAllByRole('group', { name: /^rate /i })).toHaveLength(0)
    expect(container.querySelector('a[href^="/read/"]')).not.toBeInTheDocument()
  })

  it('degrades to a generic banner when the profile lookup fails', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/profiles') return Promise.reject(new Error('offline'))
      if (url === '/v1/library') return Promise.resolve({ data: { stories: [] } })
      return Promise.resolve({ data: {} })
    })
    renderPreview()
    expect(await screen.findByText('Previewing (read-only)')).toBeInTheDocument()
  })

  it('leaks no child data for a profileId outside the guardian family', async () => {
    // The server-scoped /v1/profiles list only ever returns the guardian's own
    // family, so a profileId belonging to another family is simply absent:
    // find() yields undefined and the preview must fall back to the generic
    // banner with no foreign display name or age band. This is the client-side
    // half of the IDOR boundary the backend enforces via
    // api/deps.py::_resolve_profiles (family-scoped profile_ids); it locks in
    // that an out-of-family :profileId in the URL cannot surface another
    // child's identity or band-driven styling.
    const { container } = renderPreview('p-other-family')
    expect(await screen.findByText('Previewing (read-only)')).toBeInTheDocument()
    expect(screen.queryByText(/Mia/)).not.toBeInTheDocument()
    const root = container.querySelector('.preview-as-child')
    expect(root).not.toHaveAttribute('data-age-band')
    expect(root).not.toHaveAttribute('data-reduce-motion')
  })
})
