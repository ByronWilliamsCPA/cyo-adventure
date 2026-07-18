import 'fake-indexeddb/auto'

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { IDBFactory } from 'fake-indexeddb'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LibraryPage } from './LibraryPage'
import { percentComplete } from './bookCardUtils'
import { _resetDbHandle, cacheLibraryList, cacheStorybook } from '../offline/db'
import type { Storybook } from '../player/types'

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

// Offline-copy revocation (G8/A5): LibraryPage's only job here is to call
// reconcileOfflineCache with this fetch's authoritative ids, only on the
// success path. The actual reconciliation logic (what gets purged) is
// covered by offline/revocation.test.ts against the real IndexedDB cache;
// this file only asserts the call-site wiring.
const mockReconcile = vi.fn<(profileId: string, ids: string[]) => Promise<void>>()
mockReconcile.mockResolvedValue(undefined)
vi.mock('../offline/revocation', () => ({
  reconcileOfflineCache: (profileId: string, ids: string[]) => mockReconcile(profileId, ids),
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
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  mockReconcile.mockReset().mockResolvedValue(undefined)
})

describe('LibraryPage', () => {
  it('puts the most recently active book in the hero and the rest on the shelf', async () => {
    mockGet.mockResolvedValue({ data: { stories: [OLDER_IN_PROGRESS, IN_PROGRESS, NOT_STARTED] } })
    renderLibrary()
    const hero = await screen.findByRole('region', { name: /continue reading/i })
    expect(hero).toHaveTextContent('The Lantern')
    // UX-K5: no false linear denominator (was "5 of 10 pages explored"); a
    // branching story never visits all nodes, so the "of N" implied a wrong goal.
    expect(hero).toHaveTextContent('5 pages explored')
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

  it('falls back to the cached shelf when the fetch fails and a cache exists (UX-K1)', async () => {
    const blob: Storybook = {
      schema_version: '1.0',
      id: 's1',
      version: 2,
      title: 'The Lantern',
      metadata: {},
      variables: [],
      start_node: 'n1',
      nodes: [{ id: 'n1', body: 'x', is_ending: true, ending: null, choices: [] }],
    }
    await cacheLibraryList('p1', [IN_PROGRESS, NOT_STARTED])
    await cacheStorybook(blob) // only s1 is downloaded
    mockGet.mockRejectedValue(new Error('offline'))

    renderLibrary()

    // The offline banner and the cached shelf render instead of a dead-end.
    expect(await screen.findByText(/no internet\. these books are ready to read/i)).toBeInTheDocument()
    expect(screen.getByText('The Lantern')).toBeInTheDocument()
    // The not-downloaded book is shown but marked as needing internet.
    expect(screen.getByText(/needs internet to open/i)).toBeInTheDocument()
    expect(screen.queryByText(/lost the bookshelf/i)).not.toBeInTheDocument()
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

  describe('K6 endings tracker', () => {
    // Routes mockGet by URL so the library list and reading-history calls
    // (both GETs, fired from the same load()) can be answered differently.
    function mockLibraryAndHistory(stories: unknown[], books: unknown[]) {
      mockGet.mockImplementation((url: string) => {
        if (url.startsWith('/v1/reading-history/')) {
          return Promise.resolve({ data: { profile_id: 'p1', books } })
        }
        return Promise.resolve({ data: { stories } })
      })
    }

    it('shows the endings badge on a shelf card once the history call resolves', async () => {
      // IN_PROGRESS is the hero (most recent activity); OLDER_IN_PROGRESS is
      // the shelf card this test targets.
      mockLibraryAndHistory(
        [OLDER_IN_PROGRESS, IN_PROGRESS],
        [{ storybook_id: OLDER_IN_PROGRESS.id, endings_found: 2, total_endings: 5 }]
      )
      renderLibrary()
      const shelf = await screen.findByRole('region', { name: /more to explore/i })
      expect(await within(shelf).findByText('2 of 5 endings found')).toBeInTheDocument()
    })

    it('shows the endings badge on the hero card', async () => {
      mockLibraryAndHistory(
        [IN_PROGRESS],
        [{ storybook_id: IN_PROGRESS.id, endings_found: 1, total_endings: 3 }]
      )
      renderLibrary()
      const hero = await screen.findByRole('region', { name: /continue reading/i })
      expect(await within(hero).findByText('1 of 3 endings found')).toBeInTheDocument()
    })

    it('shows no badge (never crashes) when the history fetch fails', async () => {
      mockGet.mockImplementation((url: string) => {
        if (url.startsWith('/v1/reading-history/')) {
          return Promise.reject(new Error('history boom'))
        }
        return Promise.resolve({ data: { stories: [IN_PROGRESS] } })
      })
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      renderLibrary()
      expect(await screen.findByRole('region', { name: /continue reading/i })).toBeInTheDocument()
      expect(screen.queryByText(/endings found/i)).not.toBeInTheDocument()
      errorSpy.mockRestore()
    })

    it('shows no badge for a book with no matching history row', async () => {
      mockLibraryAndHistory([IN_PROGRESS], [])
      renderLibrary()
      expect(await screen.findByRole('region', { name: /continue reading/i })).toBeInTheDocument()
      expect(screen.queryByText(/endings found/i)).not.toBeInTheDocument()
    })
  })

  describe('K17 recommendations feed (ADR-016 rings 1-2)', () => {
    // Routes mockGet by URL so the library list and recommendations calls
    // (both GETs, fired from the same load()) can be answered differently.
    function mockLibraryAndRecommendations(stories: unknown[], items: unknown[]) {
      mockGet.mockImplementation((url: string) => {
        if (url.startsWith('/v1/recommendations/')) {
          return Promise.resolve({ data: { items } })
        }
        return Promise.resolve({ data: { stories } })
      })
    }

    it('shows a family-ring chip on the matching shelf card once the feed resolves', async () => {
      mockLibraryAndRecommendations(
        [OLDER_IN_PROGRESS, IN_PROGRESS],
        [
          {
            storybook_id: OLDER_IN_PROGRESS.id,
            title: OLDER_IN_PROGRESS.title,
            cover_url: null,
            recommender_name: 'Maya',
            rating: 5,
            ring: 'family',
          },
        ]
      )
      renderLibrary()
      const shelf = await screen.findByRole('region', { name: /more to explore/i })
      expect(await within(shelf).findByText('Maya loved this')).toBeInTheDocument()
    })

    it('shows a connection-ring chip with the "Cousin" prefix on the hero card', async () => {
      mockLibraryAndRecommendations(
        [IN_PROGRESS],
        [
          {
            storybook_id: IN_PROGRESS.id,
            title: IN_PROGRESS.title,
            cover_url: null,
            recommender_name: 'Leo',
            rating: 4,
            ring: 'connection',
          },
        ]
      )
      renderLibrary()
      const hero = await screen.findByRole('region', { name: /continue reading/i })
      expect(await within(hero).findByText('Cousin Leo loved this')).toBeInTheDocument()
    })

    it('collapses multiple recommenders for the same book into "and N more"', async () => {
      mockLibraryAndRecommendations(
        [IN_PROGRESS],
        [
          {
            storybook_id: IN_PROGRESS.id,
            title: IN_PROGRESS.title,
            cover_url: null,
            recommender_name: 'Maya',
            rating: 5,
            ring: 'family',
          },
          {
            storybook_id: IN_PROGRESS.id,
            title: IN_PROGRESS.title,
            cover_url: null,
            recommender_name: 'Leo',
            rating: 4,
            ring: 'connection',
          },
        ]
      )
      renderLibrary()
      const hero = await screen.findByRole('region', { name: /continue reading/i })
      expect(await within(hero).findByText('Maya loved this and 1 more')).toBeInTheDocument()
    })

    it('shows no chip (never crashes the shelf) when the recommendations fetch fails', async () => {
      mockGet.mockImplementation((url: string) => {
        if (url.startsWith('/v1/recommendations/')) {
          return Promise.reject(new Error('recommendations boom'))
        }
        return Promise.resolve({ data: { stories: [IN_PROGRESS] } })
      })
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      renderLibrary()
      expect(await screen.findByRole('region', { name: /continue reading/i })).toBeInTheDocument()
      expect(screen.queryByText(/loved this/i)).not.toBeInTheDocument()
      errorSpy.mockRestore()
    })

    it('shows no chip when the feed is empty', async () => {
      mockLibraryAndRecommendations([IN_PROGRESS], [])
      renderLibrary()
      expect(await screen.findByRole('region', { name: /continue reading/i })).toBeInTheDocument()
      expect(screen.queryByText(/loved this/i)).not.toBeInTheDocument()
    })

    it('shows no chip for a book with no matching recommendation entry', async () => {
      mockLibraryAndRecommendations(
        [IN_PROGRESS],
        [
          {
            storybook_id: 'some-other-book',
            title: 'Some Other Book',
            cover_url: null,
            recommender_name: 'Maya',
            rating: 5,
            ring: 'family',
          },
        ]
      )
      renderLibrary()
      expect(await screen.findByRole('region', { name: /continue reading/i })).toBeInTheDocument()
      expect(screen.queryByText(/loved this/i)).not.toBeInTheDocument()
    })
  })

  describe('offline-copy revocation call site (roadmap Phase 5, G8/A5)', () => {
    it('reconciles the offline cache with the fresh shelf ids on a successful fetch', async () => {
      mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS, NOT_STARTED] } })
      renderLibrary()
      await screen.findByRole('region', { name: /continue reading/i })
      await waitFor(() => expect(mockReconcile).toHaveBeenCalledWith('p1', ['s1', 's3']))
    })

    it('does not reconcile the offline cache when the fetch fails', async () => {
      mockGet.mockRejectedValue(new Error('boom'))
      renderLibrary()
      await screen.findByText(/lost the bookshelf/i)
      expect(mockReconcile).not.toHaveBeenCalled()
    })

    it('reconciles again when connectivity returns while the page stays mounted', async () => {
      mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS] } })
      renderLibrary()
      await screen.findByRole('region', { name: /continue reading/i })
      await waitFor(() => expect(mockReconcile).toHaveBeenCalledTimes(1))

      await act(async () => {
        window.dispatchEvent(new Event('online'))
        await Promise.resolve()
      })

      await waitFor(() => expect(mockReconcile).toHaveBeenCalledTimes(2))
    })

    it('a reconcile rejection is logged and never crashes the shelf', async () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS] } })
      mockReconcile.mockRejectedValueOnce(new Error('reconcile boom'))
      renderLibrary()
      expect(await screen.findByRole('region', { name: /continue reading/i })).toBeInTheDocument()
      await waitFor(() =>
        expect(errorSpy).toHaveBeenCalledWith('offline cache reconcile failed', 'reconcile boom')
      )
      errorSpy.mockRestore()
    })
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
