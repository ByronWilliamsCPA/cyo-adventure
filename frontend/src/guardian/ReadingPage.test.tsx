import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ReadingPage } from './ReadingPage'

const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

function mockAxiosError(props: Record<string, unknown>): Error {
  return Object.assign(new Error('mock axios error'), props)
}

const SUMMARY = {
  children: [
    {
      profile_id: 'p1',
      display_name: 'Reader A',
      books_started: 2,
      books_finished: 1,
      total_endings_found: 3,
      last_activity_at: '2026-07-15T12:00:00Z',
    },
    {
      profile_id: 'p2',
      display_name: 'Reader B',
      books_started: 0,
      books_finished: 0,
      total_endings_found: 0,
      last_activity_at: null,
    },
  ],
}

const HISTORY_P1 = {
  profile_id: 'p1',
  books: [
    {
      storybook_id: 's1',
      title: 'The Lantern',
      endings_found: 1,
      ending_ids: ['end-a'],
      total_endings: 3,
      in_progress: true,
      last_activity_at: '2026-07-15T11:00:00Z',
    },
  ],
}

function routeGet(overrides: Record<string, unknown> = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/families/me/reading-summary') {
      return Promise.resolve({ data: overrides['/v1/families/me/reading-summary'] ?? SUMMARY })
    }
    if (url === '/v1/reading-history/p1') {
      return Promise.resolve({ data: overrides['/v1/reading-history/p1'] ?? HISTORY_P1 })
    }
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ReadingPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset()
})

describe('ReadingPage', () => {
  it('renders per-child cards with signals-only stats', async () => {
    routeGet()
    renderPage()
    expect(await screen.findByText('Reader A')).toBeInTheDocument()
    const card = screen.getByText('Reader A').closest('li')
    expect(card).not.toBeNull()
    expect(within(card as HTMLElement).getByText('2')).toBeInTheDocument() // books started
    expect(within(card as HTMLElement).getByText('1')).toBeInTheDocument() // books finished
    expect(within(card as HTMLElement).getByText('3')).toBeInTheDocument() // endings found
  })

  it('shows a nudge with a Books link for a child with no reading yet', async () => {
    routeGet()
    renderPage()
    expect(await screen.findByText('Reader B')).toBeInTheDocument()
    const card = screen.getByText('Reader B').closest('li')
    expect(card).not.toBeNull()
    const link = within(card as HTMLElement).getByRole('link', {
      name: /Assign a book to get started/,
    })
    expect(link).toHaveAttribute('href', '/guardian/books')
  })

  it('expands a child and fetches per-book reading history', async () => {
    const user = userEvent.setup()
    routeGet()
    renderPage()
    const toggle = await screen.findByRole('button', { name: /Reader A/ })
    await user.click(toggle)
    expect(await screen.findByText('The Lantern')).toBeInTheDocument()
    expect(screen.getByText(/1 of 3 endings found/)).toBeInTheDocument()
    expect(screen.getByText('Still reading')).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith('/v1/reading-history/p1')
  })

  it('does not refetch history on a second expand of the same child', async () => {
    const user = userEvent.setup()
    routeGet()
    renderPage()
    const toggle = await screen.findByRole('button', { name: /Reader A/ })
    await user.click(toggle)
    await screen.findByText('The Lantern')
    await user.click(toggle) // collapse
    mockGet.mockClear()
    await user.click(toggle) // re-expand
    expect(await screen.findByText('The Lantern')).toBeInTheDocument()
    expect(mockGet).not.toHaveBeenCalledWith('/v1/reading-history/p1')
  })

  it('shows the whole-page empty state with a Books link for a childless family', async () => {
    routeGet({ '/v1/families/me/reading-summary': { children: [] } })
    renderPage()
    expect(await screen.findByText('No reading yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to Books' })).toHaveAttribute(
      'href',
      '/guardian/books'
    )
  })

  it('shows an error message when the summary load fails', async () => {
    mockGet.mockRejectedValue(mockAxiosError({ isAxiosError: true, response: { status: 500 } }))
    renderPage()
    expect(
      await screen.findByText(/We could not load your family's reading activity/)
    ).toBeInTheDocument()
  })

  it('shows an inline retry when the per-child history fetch fails', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/families/me/reading-summary') return Promise.resolve({ data: SUMMARY })
      if (url === '/v1/reading-history/p1') {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 500 } }))
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })
    renderPage()
    const toggle = await screen.findByRole('button', { name: /Reader A/ })
    await user.click(toggle)
    expect(
      await screen.findByText(/We could not load this child's book detail/)
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
