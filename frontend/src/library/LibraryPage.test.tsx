import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LibraryPage } from './LibraryPage'
import { percentComplete } from './bookCardUtils'

const mockGet = vi.fn()
const mockPost = vi.fn()
// #ASSUME: timing dependencies: LibraryPage memoizes the api client via
// useMemo/useCallback (mirroring the real useApi hook's stable reference
// when config is unchanged); a mock returning a fresh object per call would
// break that memoization and fire the load effect on every render.
// #VERIFY: keep a single stable fakeApi reference across calls (matching
// ProfilePickerPage.test.tsx's pattern) so LibraryPage's effect deps settle.
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

function renderLibrary() {
  return render(
    <MemoryRouter initialEntries={['/library/p1']}>
      <Routes>
        <Route path="/library/:profileId" element={<LibraryPage />} />
      </Routes>
    </MemoryRouter>
  )
}

const IN_PROGRESS = {
  id: 's1',
  title: 'The Lantern',
  version: 2,
  age_band: '6-8',
  tier: 1,
  reading_level_target: 2,
  node_count: 10,
  rating: null,
  progress: { current_node: 'n2', nodes_visited: 5, updated_at: '2026-07-01T10:00:00Z' },
  series_id: null,
  book_index: null,
  cover_url: null,
}
const OLDER_IN_PROGRESS = {
  ...IN_PROGRESS,
  id: 's2',
  title: 'Sky Pirates',
  progress: { current_node: 'n1', nodes_visited: 1, updated_at: '2026-06-20T10:00:00Z' },
}
const NOT_STARTED = {
  ...IN_PROGRESS,
  id: 's3',
  title: 'Acorn Detectives',
  rating: 3,
  progress: null,
}
const SERIES_BOOK = {
  ...IN_PROGRESS,
  id: 's4',
  title: 'The Fox Returns',
  series_id: 'ser1',
  book_index: 2,
  progress: null,
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
})

describe('LibraryPage', () => {
  it('puts the most recently active book in the hero and the rest on the shelf', async () => {
    mockGet.mockResolvedValue({ data: { stories: [OLDER_IN_PROGRESS, IN_PROGRESS, NOT_STARTED] } })
    renderLibrary()
    const hero = await screen.findByRole('region', { name: /continue reading/i })
    expect(hero).toHaveTextContent('The Lantern')
    expect(hero).toHaveTextContent('5 of 10 pages explored')
    const shelf = screen.getByRole('region', { name: /more to explore/i })
    expect(shelf).toHaveTextContent('Sky Pirates')
    expect(shelf).toHaveTextContent('Acorn Detectives')
    expect(shelf).toHaveTextContent('Not started')
  })

  it('links every card to the reader route', async () => {
    mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS] } })
    renderLibrary()
    const link = await screen.findByRole('link', { name: /the lantern/i })
    expect(link).toHaveAttribute('href', '/read/p1/s1/2')
  })

  it('shows the empty state when nothing is assigned', async () => {
    mockGet.mockResolvedValue({ data: { stories: [] } })
    renderLibrary()
    expect(await screen.findByText(/no books yet/i)).toBeInTheDocument()
    expect(screen.getByText(/ask a grown-up/i)).toBeInTheDocument()
    expect(screen.queryByText(/lost the bookshelf/i)).not.toBeInTheDocument()
  })

  it('shows an error state with retry on fetch failure', async () => {
    mockGet.mockRejectedValueOnce(new Error('boom'))
    mockGet.mockResolvedValueOnce({ data: { stories: [IN_PROGRESS] } })
    renderLibrary()
    const retry = await screen.findByRole('button', { name: /try again/i })
    fireEvent.click(retry)
    expect(await screen.findByRole('region', { name: /continue reading/i })).toBeInTheDocument()
  })

  it('shows the ask-a-grown-up gate on a 401, with no retry', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 401 } })
    renderLibrary()

    expect(await screen.findByText(/Time to find your grown-up/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Who's reading/i })).toHaveAttribute('href', '/kids')
    expect(screen.getByRole('link', { name: /I am a grown-up/i })).toHaveAttribute(
      'href',
      '/guardian/login'
    )
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
  })

  it('shows the forbidden copy on a 403, with a link back to the picker', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    renderLibrary()

    expect(await screen.findByText(/This bookshelf isn't yours/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Who's reading/i })).toHaveAttribute('href', '/kids')
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
    // Pins forbidden as distinct from unauthenticated: no grown-up sign-in
    // link, just the way back to the picker.
    expect(screen.queryByRole('link', { name: /I am a grown-up/i })).not.toBeInTheDocument()
  })

  it('posts a rating and re-renders the new value', async () => {
    mockGet.mockResolvedValue({ data: { stories: [NOT_STARTED] } })
    mockPost.mockResolvedValue({
      data: {
        child_profile_id: 'p1',
        storybook_id: 's3',
        value: 5,
        rated_at: '2026-07-02T00:00:00Z',
        updated_at: '2026-07-02T00:00:00Z',
      },
    })
    renderLibrary()
    fireEvent.click(await screen.findByRole('button', { name: /rate 5 stars/i }))
    expect(mockPost).toHaveBeenCalledWith('/v1/ratings', {
      profile_id: 'p1',
      storybook_id: 's3',
      value: 5,
    })
    const five = await screen.findByRole('button', { name: /rate 5 stars/i })
    expect(five).toHaveAttribute('aria-pressed', 'true')
  })

  it('keeps the previous rating when the rating POST fails', async () => {
    // NOT_STARTED is rated 3; a failed upsert must not fill the tapped star or
    // crash the shelf (rate()'s .catch keeps the previous rating).
    mockGet.mockResolvedValue({ data: { stories: [NOT_STARTED] } })
    mockPost.mockRejectedValueOnce(new Error('rate boom'))
    renderLibrary()
    fireEvent.click(await screen.findByRole('button', { name: /rate 5 stars/i }))
    expect(mockPost).toHaveBeenCalledWith('/v1/ratings', {
      profile_id: 'p1',
      storybook_id: 's3',
      value: 5,
    })
    const five = await screen.findByRole('button', { name: /rate 5 stars/i })
    expect(five).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: /rate 3 stars/i })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
  })

  it('a 401 on the rating POST surfaces the ask-a-grown-up gate', async () => {
    mockGet.mockResolvedValue({ data: { stories: [NOT_STARTED] } })
    mockPost.mockRejectedValueOnce({ isAxiosError: true, response: { status: 401 } })
    renderLibrary()
    fireEvent.click(await screen.findByRole('button', { name: /rate 5 stars/i }))

    expect(await screen.findByText(/Time to find your grown-up/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /stars/i })).not.toBeInTheDocument()
  })

  it('a non-auth rating failure keeps the shelf and the previous rating', async () => {
    mockGet.mockResolvedValue({ data: { stories: [NOT_STARTED] } })
    mockPost.mockRejectedValueOnce({ isAxiosError: true, response: { status: 500 } })
    renderLibrary()
    fireEvent.click(await screen.findByRole('button', { name: /rate 5 stars/i }))

    const five = await screen.findByRole('button', { name: /rate 5 stars/i })
    expect(five).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: /rate 3 stars/i })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    expect(screen.queryByText(/Time to find your grown-up/i)).not.toBeInTheDocument()
  })

  it('renders nothing when the route carries no profileId', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/library']}>
        <Routes>
          <Route path="/library" element={<LibraryPage />} />
        </Routes>
      </MemoryRouter>
    )
    expect(container.firstChild).toBeNull()
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('logs the raw fallback value for a non-Error, non-axios fetch rejection', async () => {
    // A thrown string has no .message and is not an AxiosError, so the
    // redacted-logging ternary must pass it through as-is.
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockGet.mockRejectedValue('socket hangup')
    renderLibrary()

    expect(await screen.findByText(/We lost the bookshelf/i)).toBeInTheDocument()
    expect(errorSpy).toHaveBeenCalledWith('library list failed', 'socket hangup')
    errorSpy.mockRestore()
  })

  it('ignores a fetch that fails after unmount (cancelled guard)', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    let rejectList!: (err: unknown) => void
    mockGet.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectList = reject
        })
    )
    const { unmount } = renderLibrary()
    unmount()
    rejectList(new Error('late boom'))

    // The redacted log still fires (it precedes the cancelled check); the
    // point is that no state write follows on the unmounted component.
    await waitFor(() => expect(errorSpy).toHaveBeenCalledWith('library list failed', 'late boom'))
    errorSpy.mockRestore()
  })

  it('ignores a fetch that resolves after unmount (cancelled guard)', async () => {
    let resolveList!: (value: unknown) => void
    mockGet.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveList = resolve
        })
    )
    const { unmount } = renderLibrary()
    unmount()
    resolveList({ data: { stories: [] } })

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).toBe('')
  })

  it('logs the raw fallback value when a rating fails with a non-Error value', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockGet.mockResolvedValue({ data: { stories: [NOT_STARTED] } })
    mockPost.mockRejectedValueOnce('rate socket hangup')
    renderLibrary()
    fireEvent.click(await screen.findByRole('button', { name: /rate 5 stars/i }))

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith('rating save failed', 'rate socket hangup')
    )
    expect(screen.getByRole('button', { name: /rate 3 stars/i })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    errorSpy.mockRestore()
  })

  it('ignores a rating 401 that lands after unmount (mounted guard)', async () => {
    mockGet.mockResolvedValue({ data: { stories: [NOT_STARTED] } })
    let rejectRate!: (err: unknown) => void
    mockPost.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectRate = reject
        })
    )
    const { unmount } = renderLibrary()
    fireEvent.click(await screen.findByRole('button', { name: /rate 5 stars/i }))
    unmount()
    rejectRate({ isAxiosError: true, response: { status: 401 } })

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(document.body.textContent).toBe('')
  })

  it('discards a rating that resolves after the page has left the ready state', async () => {
    mockGet.mockResolvedValue({ data: { stories: [NOT_STARTED] } })
    let resolveFirst!: (value: unknown) => void
    mockPost
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirst = resolve
          })
      )
      .mockRejectedValueOnce({ isAxiosError: true, response: { status: 401 } })
    renderLibrary()

    // First rating hangs in flight; the second hits a 401 and swaps the page
    // to the ask-a-grown-up gate before the first resolves.
    fireEvent.click(await screen.findByRole('button', { name: /rate 5 stars/i }))
    fireEvent.click(screen.getByRole('button', { name: /rate 4 stars/i }))
    expect(await screen.findByText(/Time to find your grown-up/i)).toBeInTheDocument()

    resolveFirst({
      data: {
        child_profile_id: 'p1',
        storybook_id: 's3',
        value: 5,
        rated_at: '2026-07-02T00:00:00Z',
        updated_at: '2026-07-02T00:00:00Z',
      },
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    // The stale success must not resurrect the shelf over the gate.
    expect(screen.getByText(/Time to find your grown-up/i)).toBeInTheDocument()
  })

  it('rating one book leaves the other books untouched', async () => {
    mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS, NOT_STARTED] } })
    mockPost.mockResolvedValue({
      data: {
        child_profile_id: 'p1',
        storybook_id: 's3',
        value: 5,
        rated_at: '2026-07-02T00:00:00Z',
        updated_at: '2026-07-02T00:00:00Z',
      },
    })
    renderLibrary()
    const shelf = await screen.findByRole('region', { name: /more to explore/i })
    fireEvent.click(within(shelf).getByRole('button', { name: /rate 5 stars/i }))

    await waitFor(() =>
      expect(within(shelf).getByRole('button', { name: /rate 5 stars/i })).toHaveAttribute(
        'aria-pressed',
        'true'
      )
    )
    // The hero (a different book) went through the non-matching map arm and
    // is untouched by the shelf book's rating.
    const hero = screen.getByRole('region', { name: /continue reading/i })
    expect(hero).toHaveTextContent('The Lantern')
  })

  it('renders the shelf non-hero started book with a plain progress bar and no pages-explored label', async () => {
    mockGet.mockResolvedValue({ data: { stories: [OLDER_IN_PROGRESS, IN_PROGRESS] } })
    renderLibrary()
    const shelf = await screen.findByRole('region', { name: /more to explore/i })
    const progressbars = within(shelf).getAllByRole('progressbar')
    expect(progressbars.length).toBeGreaterThan(0)
    expect(within(shelf).queryByText(/of \d+ pages explored/i)).not.toBeInTheDocument()
  })

  it('tapping Ask for the next book on a series book opens the request form anchored to it', async () => {
    mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS, SERIES_BOOK] } })
    mockPost.mockResolvedValue({ data: { id: 'req1', status: 'pending' } })
    renderLibrary()

    const shelf = await screen.findByRole('region', { name: /more to explore/i })
    fireEvent.click(within(shelf).getByRole('button', { name: /ask for the next book/i }))

    expect(await screen.findByText(/continuing: the fox returns/i)).toBeInTheDocument()
    // Anchor mode replaces the series-name input with the continuing chip.
    expect(screen.queryByLabelText(/part of a series\? give it a name!/i)).not.toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'More fox adventures' } })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/story-requests', {
        profile_id: 'p1',
        request_text: 'More fox adventures',
        anchor_storybook_id: 's4',
      })
    )
  })
})

describe('percentComplete', () => {
  it('clamps at 100 when nodes_visited exceeds node_count', () => {
    expect(
      percentComplete({
        ...IN_PROGRESS,
        node_count: 5,
        progress: { current_node: 'n2', nodes_visited: 10, updated_at: '2026-07-01T10:00:00Z' },
      })
    ).toBe(100)
  })

  it('returns 0 when node_count is 0', () => {
    expect(percentComplete({ ...IN_PROGRESS, node_count: 0 })).toBe(0)
  })

  it('returns 0 when progress is null', () => {
    expect(percentComplete({ ...IN_PROGRESS, progress: null })).toBe(0)
  })
})
