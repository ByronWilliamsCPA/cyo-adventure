import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BooksPage } from './BooksPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

/**
 * Real axios rejections are `AxiosError` instances (an `Error` subclass); this
 * builds a real `Error` carrying the same shape axios attaches (`isAxiosError`,
 * `response`) so the mocked rejection is faithful to what the code under test
 * actually receives.
 */
function mockAxiosError(props: Record<string, unknown>): Error {
  return Object.assign(new Error('mock axios error'), props)
}

const PROFILES = {
  profiles: [
    {
      id: 'p1',
      display_name: 'Reader A',
      age_band: '10-13',
      reading_level_cap: 99,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    },
    {
      id: 'p2',
      display_name: 'Reader A2',
      age_band: '8-11',
      reading_level_cap: 99,
      avatar: 'owl',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    },
  ],
}

const BOOKS = {
  books: [
    {
      storybook_id: 's1',
      title: 'The Lantern',
      version: 2,
      age_band: '8-11',
      screened: true,
      flagged_count: 1,
      assigned_profile_ids: ['p1'],
      visibility: 'family' as const,
      themes: ['friendship', 'courage'],
      content_flags: { violence: 'mild', scariness: 'none', peril: 'moderate' },
    },
  ],
}

// A helper that routes each GET path to a canned response.
function routeGet(overrides: Record<string, unknown> = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/guardian/books') {
      return Promise.resolve({ data: overrides['/v1/guardian/books'] ?? BOOKS })
    }
    if (url === '/v1/profiles') {
      return Promise.resolve({ data: overrides['/v1/profiles'] ?? PROFILES })
    }
    if (url.endsWith('/assignments')) {
      return Promise.resolve({ data: { storybook_id: 's1', profile_ids: ['p1'] } })
    }
    if (url.endsWith('/content-summary')) {
      return Promise.resolve({
        data: {
          storybook_id: 's1',
          version: 2,
          screened: true,
          summary: null,
          flagged_count: 1,
          findings: [],
        },
      })
    }
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

function renderPage() {
  return render(
    <MemoryRouter>
      <BooksPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset().mockResolvedValue({
    data: { storybook_id: 's1', profile_ids: ['p1', 'p2'] },
  })
})

describe('BooksPage', () => {
  it('lists published books with a content badge and assignment status', async () => {
    routeGet()
    renderPage()
    expect(await screen.findByText('The Lantern')).toBeInTheDocument()
    // FlagBadge renders the count-inclusive label passed by ContentBadge
    // (`${book.flagged_count} flagged`), not the bare tone label; asserting
    // the count keeps this test true to what FlagBadge actually renders.
    expect(screen.getByText('1 flagged')).toBeInTheDocument()
    expect(screen.getByText(/Assigned to: Reader A$/)).toBeInTheDocument()
  })

  it('shows the age band next to each book', async () => {
    routeGet()
    renderPage()
    expect(await screen.findByText('Ages 8-11')).toBeInTheDocument()
  })

  it('omits the age band chip instead of rendering a bare "Ages" when age_band is empty', async () => {
    routeGet({
      '/v1/guardian/books': {
        books: [{ ...BOOKS.books[0], age_band: '' }],
      },
    })
    renderPage()
    await screen.findByText('The Lantern')
    expect(screen.queryByText(/^Ages/)).not.toBeInTheDocument()
  })

  it('opens the book-details dialog with themes and content flags', async () => {
    const user = userEvent.setup()
    routeGet()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /View details for The Lantern/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('friendship, courage')).toBeInTheDocument()
    expect(within(dialog).getByText(/Violence: mild/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Peril: moderate/)).toBeInTheDocument()
    expect(within(dialog).getByText('1 flagged')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: /^Close$/ }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('opens the assign dialog and assigns a sibling', async () => {
    const user = userEvent.setup()
    routeGet()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /^Assign The Lantern$/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('checkbox', { name: /Reader A2/ }))
    await user.click(within(dialog).getByRole('button', { name: /^Assign$/ }))
    expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/assignments', {
      profile_ids: ['p2'],
    })
    // After assigning, the row reflects both children.
    expect(await screen.findByText(/Reader A, Reader A2/)).toBeInTheDocument()
  })

  it('shows the empty state when there are no published books', async () => {
    routeGet({ '/v1/guardian/books': { books: [] } })
    renderPage()
    expect(await screen.findByText(/No published books yet/)).toBeInTheDocument()
  })

  it('shows a forbidden notice when the endpoint returns 403 (admin)', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/guardian/books') {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 403 } }))
      }
      return Promise.resolve({ data: PROFILES })
    })
    renderPage()
    expect(await screen.findByText(/Assigning books is handled by a guardian/)).toBeInTheDocument()
  })

  it('shows a generic error on a non-403 failure', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/guardian/books') {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 500 } }))
      }
      return Promise.resolve({ data: PROFILES })
    })
    renderPage()
    expect(await screen.findByText(/We could not load your family's books/)).toBeInTheDocument()
  })

  it('retries the load in place when Try again is clicked (UX-C1)', async () => {
    let attempt = 0
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/guardian/books') {
        attempt += 1
        if (attempt === 1) {
          return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 500 } }))
        }
        return Promise.resolve({ data: BOOKS })
      }
      return Promise.resolve({ data: PROFILES })
    })
    renderPage()
    const retry = await screen.findByRole('button', { name: /try again/i })
    await userEvent.click(retry)
    // The second load succeeds and the books heading renders instead of the error.
    expect(await screen.findByRole('heading', { name: 'Books' })).toBeInTheDocument()
    expect(screen.queryByText(/We could not load/)).not.toBeInTheDocument()
  })

  it('surfaces unresolved assigned ids instead of collapsing to "No one yet"', async () => {
    // s1 is assigned to p1 (known) plus p9 (e.g. a since-deleted profile not in
    // the profiles list); s2 is assigned only to the unknown p9. A book that IS
    // assigned must never render "No one yet"; unresolved ids show as a count.
    routeGet({
      '/v1/guardian/books': {
        books: [
          { ...BOOKS.books[0], assigned_profile_ids: ['p1', 'p9'] },
          {
            storybook_id: 's2',
            title: 'The Compass',
            version: 1,
            age_band: '8-11',
            screened: false,
            flagged_count: 0,
            assigned_profile_ids: ['p9'],
            visibility: 'family' as const,
          },
        ],
      },
    })
    renderPage()
    expect(await screen.findByText(/Assigned to: Reader A, 1 unknown profile$/)).toBeInTheDocument()
    expect(screen.getByText(/Assigned to: 1 unknown profile$/)).toBeInTheDocument()
    expect(screen.queryByText(/Assigned to: No one yet/)).not.toBeInTheDocument()
  })

  it('badges catalog books and not family books', async () => {
    routeGet({
      '/v1/guardian/books': {
        books: [
          { ...BOOKS.books[0], storybook_id: 's-fam', title: 'Ours', visibility: 'family' },
          { ...BOOKS.books[0], storybook_id: 's-cat', title: 'Shared', visibility: 'catalog' },
        ],
      },
    })
    renderPage()
    const shared = (await screen.findByText('Shared')).closest('li')
    expect(shared).not.toBeNull()
    expect(within(shared as HTMLElement).getByText('Catalog')).toBeInTheDocument()
    const ours = screen.getByText('Ours').closest('li')
    expect(within(ours as HTMLElement).queryByText('Catalog')).not.toBeInTheDocument()
  })
})
