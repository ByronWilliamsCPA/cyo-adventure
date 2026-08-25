import 'fake-indexeddb/auto'

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IDBFactory } from 'fake-indexeddb'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LibraryPage } from './LibraryPage'
import { percentComplete } from './bookCardUtils'
import { _resetDbHandle, cacheLibraryList, cacheStorybook } from '../offline/db'
import * as deviceIdModule from '../offline/deviceId'
import type { Storybook } from '../player/types'

const mockGet = vi.fn()
const mockPost = vi.fn()
// `delete` carries the G15 offline-purge report (makeRemoveDownload), the
// only verb LibraryPage issues outside the shelf fetch and rating POST.
const mockDelete = vi.fn()
// #ASSUME: timing dependencies: LibraryPage memoizes the api client via
// useMemo/useCallback (mirroring the real useApi hook's stable reference
// when config is unchanged); a mock returning a fresh object per call would
// break that memoization and fire the load effect on every render.
// #VERIFY: keep a single stable fakeApi reference across calls (matching
// ProfilePickerPage.test.tsx's pattern) so LibraryPage's effect deps settle.
const fakeApi = { get: mockGet, post: mockPost, delete: mockDelete }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

// Offline-copy revocation (G8/A5): LibraryPage's only job here is to call
// reconcileOfflineCache with this fetch's authoritative ids, only on the
// success path. The actual reconciliation logic (what gets purged) is
// covered by offline/revocation.test.ts against the real IndexedDB cache;
// this file only asserts the call-site wiring.
// The options argument is forwarded, not dropped: G15's `reportRemoval`
// callback rides in it, and a mock that swallowed it could never exercise
// LibraryPage's own side of that wiring (the callback would simply never be
// invoked, and a test asserting on it would pass for the wrong reason).
type ReconcileOptions = { reportRemoval?: (storybookId: string) => void }
const mockReconcile =
  vi.fn<(profileId: string, ids: string[], options?: ReconcileOptions) => Promise<void>>()
mockReconcile.mockResolvedValue(undefined)
// Content-staleness eviction rides in the same module and the same success
// block. Mocked alongside the reconcile rather than left out: `vi.mock`
// replaces the WHOLE module, so an omitted export is `undefined` at the call
// site, not a harmless no-op.
type StaleItem = { id: string; version: number; content_hash?: string }
const mockEvictStale =
  vi.fn<
    (items: readonly StaleItem[]) => Promise<{ changed: number; unverified: number; fresh: number }>
  >()
mockEvictStale.mockResolvedValue({ changed: 0, unverified: 0, fresh: 0 })
vi.mock('../offline/revocation', () => ({
  reconcileOfflineCache: (profileId: string, ids: string[], options?: ReconcileOptions) =>
    mockReconcile(profileId, ids, options),
  evictStaleOfflineBooks: (items: readonly StaleItem[]) => mockEvictStale(items),
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

function renderLibraryReadOnly() {
  return render(
    <MemoryRouter initialEntries={['/library/p1']}>
      <Routes>
        <Route path="/library/:profileId" element={<LibraryPage readOnly />} />
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
  mockDelete.mockReset().mockResolvedValue({ data: undefined })
  mockReconcile.mockReset().mockResolvedValue(undefined)
  mockEvictStale.mockReset().mockResolvedValue({ changed: 0, unverified: 0, fresh: 0 })
  // W4.3: clear any pending download-refusal flag so one test's banner never
  // leaks into the next.
  localStorage.clear()
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

  it('opens and focuses the request form from the shelf end-cap tile', async () => {
    mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS, NOT_STARTED] } })
    renderLibrary()
    const shelf = await screen.findByRole('region', { name: /more to explore/i })

    // The form starts closed; the end-cap tile lives inside the shelf grid.
    expect(
      screen.queryByRole('textbox', { name: /what should your story be about/i })
    ).not.toBeInTheDocument()
    fireEvent.click(within(shelf).getByRole('button', { name: /ask for a new story/i }))

    const requestField = await screen.findByRole('textbox', {
      name: /what should your story be about/i,
    })
    expect(requestField).toBeInTheDocument()
    // Wayfinding: the tap moved focus to the far-away form container, so a
    // keyboard or screen-reader user lands on the newly revealed form rather
    // than being stranded on the shelf tile. Resolve that container by the
    // attribute that makes it a programmatic focus target (tabindex="-1", the
    // only one on this path) rather than by its CSS class name, then assert it
    // holds focus DIRECTLY. `expect(document.activeElement).toContainElement(...)`
    // would not do: document.body contains the field too, so that form passes
    // even when the focus move never happened.
    const requestContainer = requestField.closest('[tabindex="-1"]')
    expect(requestContainer).not.toBeNull()
    expect(requestContainer).toHaveFocus()
  })

  it('titles the shelf "Pick a book!" when nothing has been started yet', async () => {
    mockGet.mockResolvedValue({ data: { stories: [NOT_STARTED, SERIES_BOOK] } })
    renderLibrary()
    const shelf = await screen.findByRole('region', { name: /more to explore/i })

    // No hero without progress; the lone shelf's heading becomes the call to
    // action while the region keeps its stable accessible name.
    expect(screen.queryByRole('region', { name: /continue reading/i })).not.toBeInTheDocument()
    expect(within(shelf).getByRole('heading', { name: 'Pick a book!' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'More to Explore' })).not.toBeInTheDocument()
  })

  it('titles the hero "Keep reading" for an unfinished book', async () => {
    mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS, NOT_STARTED] } })
    renderLibrary()
    const hero = await screen.findByRole('region', { name: /continue reading/i })
    expect(within(hero).getByRole('heading', { name: 'Keep reading' })).toBeInTheDocument()
  })

  it('titles the hero "Read it again?" once its book is finished', async () => {
    const finished = {
      ...IN_PROGRESS,
      progress: { ...IN_PROGRESS.progress, completed: true },
    }
    mockGet.mockResolvedValue({ data: { stories: [finished, NOT_STARTED] } })
    renderLibrary()
    const hero = await screen.findByRole('region', { name: /continue reading/i })
    expect(within(hero).getByRole('heading', { name: 'Read it again?' })).toBeInTheDocument()
    expect(within(hero).queryByRole('heading', { name: 'Keep reading' })).not.toBeInTheDocument()
  })

  it('shows the empty state when nothing is assigned', async () => {
    mockGet.mockResolvedValue({ data: { stories: [] } })
    renderLibrary()
    expect(await screen.findByText(/no books yet/i)).toBeInTheDocument()
    expect(screen.getByText(/ask a grown-up/i)).toBeInTheDocument()
    expect(screen.queryByText(/lost the bookshelf/i)).not.toBeInTheDocument()
  })

  it('shows an error state with retry on fetch failure', async () => {
    // W3.2 added a second, parallel GET (progress) fired from its own
    // mount effect; route by URL so the Once-queue below applies to the
    // LIBRARY LIST call specifically (the one the retry button drives),
    // not whichever endpoint's effect happens to fire first.
    let libraryCall = 0
    mockGet.mockImplementation((url: string) => {
      if (url !== '/v1/library') return Promise.resolve({ data: {} })
      libraryCall += 1
      return libraryCall === 1
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: { stories: [IN_PROGRESS] } })
    })
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
    expect(
      await screen.findByText(/no internet\. these books are ready to read/i)
    ).toBeInTheDocument()
    expect(screen.getByText('The Lantern')).toBeInTheDocument()
    // The not-downloaded book is shown but marked as needing internet.
    expect(screen.getByText(/needs internet to open/i)).toBeInTheDocument()
    expect(screen.queryByText(/lost the bookshelf/i)).not.toBeInTheDocument()
  })

  it('hides the request affordances on the offline shelf (they need the network)', async () => {
    await cacheLibraryList('p1', [IN_PROGRESS, SERIES_BOOK])
    mockGet.mockRejectedValue(new Error('offline'))

    renderLibrary()

    expect(await screen.findByText(/no internet\./i)).toBeInTheDocument()
    // Online, all of these would render (SERIES_BOOK is series-tagged);
    // offline they could only dead-end in a failure message or a silently
    // dropped write, so none are offered.
    expect(screen.queryByRole('button', { name: /request a story/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ask for the next book/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ask for a new story/i })).not.toBeInTheDocument()
    expect(screen.queryAllByRole('group', { name: /^rate /i })).toHaveLength(0)
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
    // Asserted by URL, not by total call count: W3.2's progress fetch and
    // Task 8's active-character fetch each fire from their own parallel mount
    // effect alongside the library list call, and the point of this test (no
    // state write survives unmount) is unaffected by which endpoints fired.
    // A raw count would break on any unrelated added or de-duplicated fetch.
    const urls = mockGet.mock.calls.map((call) => call[0] as string)
    expect(urls).toContain('/v1/library')
    expect(urls).toContain('/v1/me/progress')
    expect(urls).toContain('/v1/characters')
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

  describe('readOnly (guardian preview-as-child)', () => {
    it('renders the shelf with no rating, request-a-story form, or Reader links', async () => {
      mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS, SERIES_BOOK] } })
      const { container } = renderLibraryReadOnly()
      await screen.findByRole('region', { name: /continue reading/i })

      expect(screen.queryAllByRole('group', { name: /^rate /i })).toHaveLength(0)
      expect(screen.queryByRole('region', { name: /request a story/i })).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: /ask for the next book/i })
      ).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /ask for a new story/i })).not.toBeInTheDocument()
      expect(container.querySelector('a[href^="/read/"]')).not.toBeInTheDocument()
    })

    it('does not render the request-story form on an empty shelf either', async () => {
      mockGet.mockResolvedValue({ data: { stories: [] } })
      renderLibraryReadOnly()
      await screen.findByText(/no books yet/i)
      expect(screen.queryByRole('region', { name: /request a story/i })).not.toBeInTheDocument()
    })
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

    // W3.2: the gallery BUTTON is gated on reading history, the gallery's
    // CONTENTS come from /v1/me/progress. Two fetches, and only one of them
    // has to succeed for the button to appear, so the failure below is the
    // one where the screen contradicts itself: the card badge says "2 of 5"
    // and the modal it opens says nothing has been found.
    it('does not report an empty ending collection when the progress fetch failed', async () => {
      mockGet.mockImplementation((url: string) => {
        if (url === '/v1/me/progress') return Promise.reject(new Error('progress boom'))
        if (url.startsWith('/v1/reading-history/')) {
          return Promise.resolve({
            data: {
              profile_id: 'p1',
              books: [{ storybook_id: IN_PROGRESS.id, endings_found: 2, total_endings: 5 }],
            },
          })
        }
        return Promise.resolve({ data: { stories: [IN_PROGRESS] } })
      })
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      renderLibrary()
      const hero = await screen.findByRole('region', { name: /continue reading/i })
      // The badge proves the child HAS found endings, which is exactly what
      // makes the empty-state copy a lie rather than merely unhelpful.
      expect(await within(hero).findByText('2 of 5 endings found')).toBeInTheDocument()

      fireEvent.click(await within(hero).findByTestId('open-endings-gallery'))
      expect(await screen.findByTestId('endings-gallery-unavailable')).toBeInTheDocument()
      expect(screen.queryByText(/keep reading to start finding endings/i)).not.toBeInTheDocument()
      errorSpy.mockRestore()
    })

    it('still shows the real empty state when progress loads and is genuinely empty', async () => {
      mockGet.mockImplementation((url: string) => {
        if (url === '/v1/me/progress') {
          return Promise.resolve({ data: { badges: [], books: [], totals: null } })
        }
        if (url.startsWith('/v1/reading-history/')) {
          return Promise.resolve({
            data: {
              profile_id: 'p1',
              books: [{ storybook_id: IN_PROGRESS.id, endings_found: 0, total_endings: 5 }],
            },
          })
        }
        return Promise.resolve({ data: { stories: [IN_PROGRESS] } })
      })
      renderLibrary()
      const hero = await screen.findByRole('region', { name: /continue reading/i })
      fireEvent.click(await within(hero).findByTestId('open-endings-gallery'))
      // The point of the pair: 'unavailable' must not become the answer to
      // every empty gallery, or it just relabels the same wrong message.
      await waitFor(() => {
        expect(screen.queryByTestId('endings-gallery-unavailable')).not.toBeInTheDocument()
      })
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
      await waitFor(() => expect(mockReconcile).toHaveBeenCalled())
      const [calledProfileId, calledIds, calledOptions] = mockReconcile.mock.calls[0]
      expect(calledProfileId).toBe('p1')
      expect(calledIds).toEqual(['s1', 's3'])
      // The G15 reporter rides along on every reconcile, so a purge always has
      // somewhere to report to (see the offline-purge reporting suite below).
      expect(typeof calledOptions?.reportRemoval).toBe('function')
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

    it('evicts stale offline content with the full shelf items on a successful fetch', async () => {
      // Passed the ITEMS, not the ids: the content identity the eviction
      // compares against lives on the item, so an ids-only call would silently
      // verify nothing while still looking wired.
      mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS, NOT_STARTED] } })
      renderLibrary()
      await screen.findByRole('region', { name: /continue reading/i })
      await waitFor(() => expect(mockEvictStale).toHaveBeenCalledTimes(1))
      const [calledItems] = mockEvictStale.mock.calls[0]
      expect(calledItems.map((item) => item.id)).toEqual(['s1', 's3'])
      expect(calledItems[0]).toHaveProperty('version')
    })

    it('does not evict stale offline content when the fetch fails', async () => {
      // Same call-site invariant as the reconcile above: both purge local
      // state on the strength of this response being authoritative, so neither
      // may ever run from the catch branch.
      mockGet.mockRejectedValue(new Error('boom'))
      renderLibrary()
      await screen.findByText(/lost the bookshelf/i)
      expect(mockEvictStale).not.toHaveBeenCalled()
    })

    it('a stale-eviction rejection is logged and never crashes the shelf', async () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS] } })
      mockEvictStale.mockRejectedValueOnce(new Error('evict boom'))
      renderLibrary()
      expect(await screen.findByRole('region', { name: /continue reading/i })).toBeInTheDocument()
      await waitFor(() =>
        expect(errorSpy).toHaveBeenCalledWith('offline stale-content eviction failed', 'evict boom')
      )
      errorSpy.mockRestore()
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

  describe('offline download budget refusal banner (W4.3, D20)', () => {
    it('shows the kid-friendly full-shelf notice once, consuming the pending refusal flag', async () => {
      localStorage.setItem('offline_download_refusal', String(Date.now()))
      mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS] } })
      renderLibrary()
      expect(
        await screen.findByText("This tablet's bookshelf is full. Ask a grown-up to remove a book.")
      ).toBeInTheDocument()
      // Consumed: a stored refusal is gone after being read once.
      expect(localStorage.getItem('offline_download_refusal')).toBeNull()
    })

    it('shows no notice when no download was ever refused', async () => {
      mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS] } })
      renderLibrary()
      await screen.findByRole('region', { name: /continue reading/i })
      expect(
        screen.queryByText("This tablet's bookshelf is full. Ask a grown-up to remove a book.")
      ).not.toBeInTheDocument()
    })

    it('reports an eviction as its own notice, not as the full-shelf refusal', async () => {
      // Opposite outcomes: the new book WAS saved. Telling a child the shelf
      // is full when it is not, and saying nothing at all when one of their
      // downloaded books just disappeared, are both wrong.
      localStorage.setItem('offline_download_eviction', String(Date.now()))
      mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS] } })
      renderLibrary()
      expect(await screen.findByText(/We made room for your new book/)).toBeInTheDocument()
      expect(
        screen.queryByText("This tablet's bookshelf is full. Ask a grown-up to remove a book.")
      ).not.toBeInTheDocument()
      expect(localStorage.getItem('offline_download_eviction')).toBeNull()
    })
  })
})

/**
 * Where the active character comes from. KidShell already resolves it for
 * the library route, so the routed kid library must reuse that lookup rather
 * than issue a second identical GET /v1/characters on the surface most
 * likely to be on a slow home connection. The guardian preview-as-child
 * route has no KidShell above it, so the local fallback has to stay.
 */
describe('LibraryPage active-character source', () => {
  const LUNA = {
    id: 'char-1',
    profile_id: 'p1',
    name: 'Luna',
    archetype: 'scout',
    look: 'avatar_01',
    is_active: true,
    books_completed: 0,
    attributes: {},
    seed_var_state: {},
    created_at: '2026-08-01T00:00:00Z',
    retired_at: null,
  }

  function routeGets() {
    mockGet.mockImplementation((url: string) =>
      url === '/v1/characters'
        ? Promise.resolve({ data: { characters: [LUNA] } })
        : Promise.resolve({ data: { stories: [IN_PROGRESS] } })
    )
  }

  function characterCalls() {
    return mockGet.mock.calls.filter((call) => call[0] === '/v1/characters')
  }

  it("reuses the shell's active character instead of fetching its own", async () => {
    routeGets()
    render(
      <MemoryRouter initialEntries={['/library/p1']}>
        <Routes>
          <Route
            element={
              <Outlet
                context={{
                  activeCharacter: {
                    state: { status: 'ready', character: LUNA },
                    refresh: vi.fn(),
                  },
                }}
              />
            }
          >
            <Route path="/library/:profileId" element={<LibraryPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    // The strip renders from the shell's value...
    expect(await screen.findByText('Luna')).toBeInTheDocument()
    // ...and the page issued no character fetch of its own to get it.
    expect(characterCalls()).toHaveLength(0)
  })

  it('fetches its own active character when mounted outside KidShell', async () => {
    routeGets()
    // The guardian preview-as-child mount: no shell above, so the Outlet
    // context is null and the local hook is the only source. Asserted
    // through the non-readOnly render, since readOnly suppresses the strip.
    renderLibrary()

    expect(await screen.findByText('Luna')).toBeInTheDocument()
    expect(characterCalls()).toHaveLength(1)
    expect(characterCalls()[0]).toEqual(['/v1/characters', { params: { profile_id: 'p1' } }])
  })

  it('issues no character fetch at all in readOnly mode (guardian preview-as-child)', async () => {
    // PreviewAsChildPage mounts LibraryPage readOnly, outside KidShell, so
    // (before this fix) the local-fallback branch above still ran and hit
    // GET /v1/characters even though `!readOnly && ...` means the whole
    // character section, and this fetch's result, is never rendered.
    routeGets()
    renderLibraryReadOnly()

    // Something else that only resolves after the initial render settles,
    // so the assertion below is not racing the mount.
    await screen.findByText(IN_PROGRESS.title)
    expect(characterCalls()).toHaveLength(0)
  })
})

/**
 * ADR-028 / gate-rework: the character creator gates a book, not the
 * library route (KidShell no longer gates there at all, see KidShell.test.tsx).
 * A book shows the creator first only when it declares `accepts_character:
 * true` AND the profile's active character status is exactly `'none'`; every
 * other combination goes straight to the read, failing open rather than
 * ever locking a child out of a book they are allowed to read.
 */
describe('LibraryPage character gate', () => {
  const READY_CHARACTER = {
    id: 'char-2',
    profile_id: 'p1',
    name: 'Rex',
    archetype: 'guardian',
    look: 'avatar_02',
    is_active: true,
    books_completed: 0,
    attributes: {},
    seed_var_state: {},
    created_at: '2026-08-01T00:00:00Z',
    retired_at: null,
  }
  const NEW_CHARACTER = {
    id: 'char-3',
    profile_id: 'p1',
    name: 'Rex',
    archetype: 'scout',
    look: 'avatar_01',
    is_active: true,
    books_completed: 0,
    attributes: {},
    seed_var_state: {},
    created_at: '2026-08-08T00:00:00Z',
    retired_at: null,
  }
  const GATED_BOOK = {
    ...NOT_STARTED,
    id: 'sg1',
    title: 'The Gated Quest',
    accepts_character: true,
  }
  const FALSE_GATE_BOOK = {
    ...NOT_STARTED,
    id: 'su1',
    title: 'The Open Trail',
    accepts_character: false,
  }
  const UNDEFINED_GATE_BOOK = { ...NOT_STARTED, id: 'sn1', title: 'The Undeclared Path' }

  /**
   * Renders LibraryPage under an Outlet that hands down a fixed
   * active-character state (mirroring the "LibraryPage active-character
   * source" describe block above), plus a real `/read/...` route so a click
   * that should navigate straight through can be observed landing there.
   */
  function renderWithCharacterState(
    state: { status: string; character?: unknown },
    items: unknown[]
  ) {
    mockGet.mockImplementation((url: string) =>
      url === '/v1/characters'
        ? Promise.resolve({ data: { characters: [] } })
        : Promise.resolve({ data: { stories: items } })
    )
    return render(
      <MemoryRouter initialEntries={['/library/p1']}>
        <Routes>
          <Route element={<Outlet context={{ activeCharacter: { state, refresh: vi.fn() } }} />}>
            <Route path="/library/:profileId" element={<LibraryPage />} />
            <Route path="/read/:profileId/:storybookId/:version" element={<div>Reader Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )
  }

  it('shows the creator, not the read, for accepts_character true + status none', async () => {
    renderWithCharacterState({ status: 'none' }, [GATED_BOOK])
    fireEvent.click(await screen.findByRole('link', { name: /the gated quest/i }))

    expect(await screen.findByRole('heading', { name: /make your character/i })).toBeInTheDocument()
    expect(screen.queryByText('Reader Page')).not.toBeInTheDocument()
  })

  it('a child who taps a gated book by accident can get back to the shelf', async () => {
    // Regression: tapping a gated book used to have no way out other than
    // browser Back, which leaves /library/:profileId entirely since
    // pendingRead is local state, not a route.
    const user = userEvent.setup()
    renderWithCharacterState({ status: 'none' }, [GATED_BOOK])
    fireEvent.click(await screen.findByRole('link', { name: /the gated quest/i }))
    await screen.findByRole('heading', { name: /make your character/i })

    await user.click(screen.getByRole('button', { name: /never mind/i }))

    // Back on the shelf, not stuck in the creator and not navigated away to
    // the read.
    expect(await screen.findByRole('link', { name: /the gated quest/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /make your character/i })).not.toBeInTheDocument()
    expect(screen.queryByText('Reader Page')).not.toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('goes straight to the read for accepts_character false + status none', async () => {
    renderWithCharacterState({ status: 'none' }, [FALSE_GATE_BOOK])
    fireEvent.click(await screen.findByRole('link', { name: /the open trail/i }))

    expect(await screen.findByText('Reader Page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /make your character/i })).not.toBeInTheDocument()
  })

  it('goes straight to the read for accepts_character undefined + status none', async () => {
    renderWithCharacterState({ status: 'none' }, [UNDEFINED_GATE_BOOK])
    fireEvent.click(await screen.findByRole('link', { name: /the undeclared path/i }))

    expect(await screen.findByText('Reader Page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /make your character/i })).not.toBeInTheDocument()
  })

  it('goes straight to the read for accepts_character true + status ready', async () => {
    renderWithCharacterState({ status: 'ready', character: READY_CHARACTER }, [GATED_BOOK])
    fireEvent.click(await screen.findByRole('link', { name: /the gated quest/i }))

    expect(await screen.findByText('Reader Page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /make your character/i })).not.toBeInTheDocument()
  })

  it('goes straight to the read for accepts_character true + status loading (fail-open)', async () => {
    renderWithCharacterState({ status: 'loading' }, [GATED_BOOK])
    fireEvent.click(await screen.findByRole('link', { name: /the gated quest/i }))

    expect(await screen.findByText('Reader Page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /make your character/i })).not.toBeInTheDocument()
  })

  it('lands in the read the child originally chose after creating a character', async () => {
    mockPost.mockResolvedValueOnce({ data: NEW_CHARACTER })
    const user = userEvent.setup()
    renderWithCharacterState({ status: 'none' }, [GATED_BOOK])
    fireEvent.click(await screen.findByRole('link', { name: /the gated quest/i }))
    await screen.findByRole('heading', { name: /make your character/i })

    // Same interaction sequence as CharacterCreator.test.tsx's own submit
    // test: userEvent (not fireEvent) is what actually drives these
    // controlled radio inputs' onChange handlers.
    await user.type(screen.getByLabelText("What's their name?"), 'Rex')
    await user.click(screen.getByRole('radio', { name: /Scout/ }))
    await user.click(screen.getByRole('radio', { name: /^Look 1\b/ }))
    await user.click(screen.getByRole('button', { name: /start my adventure/i }))

    // Lands on the exact read the child chose before the creator interrupted
    // them (GATED_BOOK's own id and version), not just any read route.
    expect(await screen.findByText('Reader Page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /make your character/i })).not.toBeInTheDocument()
  })

  it('still renders and behaves as a real link for a non-gated book, which is what the e2e smoke depends on', async () => {
    renderWithCharacterState({ status: 'none' }, [FALSE_GATE_BOOK])
    const link = await screen.findByRole('link', { name: /the open trail/i })
    expect(link).toHaveAttribute(
      'href',
      `/read/p1/${FALSE_GATE_BOOK.id}/${FALSE_GATE_BOOK.version}`
    )

    fireEvent.click(link)
    expect(await screen.findByText('Reader Page')).toBeInTheDocument()
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

// G15 storage/download view: LibraryPage owns the reporting side of the
// offline purge, handing reconcileOfflineCache a `reportRemoval` callback
// that issues the DELETE. Its own describe block because both tests install
// a module spy on getOrCreateDeviceId; this suite configures no global mock
// restoration, so a leaked spy would silently follow the rest of the file.
describe('LibraryPage offline-purge reporting (G15)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('reports a purged book to the guardian download view', async () => {
    vi.spyOn(deviceIdModule, 'getOrCreateDeviceId').mockReturnValue('device-fixed')
    mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS] } })
    mockReconcile.mockImplementation((_profileId, _ids, options) => {
      options?.reportRemoval?.('s9')
      return Promise.resolve()
    })

    renderLibrary()
    await screen.findByText('The Lantern')

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith('/v1/device-downloads', {
        params: { device_id: 'device-fixed', storybook_id: 's9' },
      })
    })
  })

  it('finishes the shelf load when the device-id lookup throws during a purge', async () => {
    // Containment, end to end: a device id this browser cannot mint is a
    // diagnostic failure, and the child must never see it. This asserts the
    // observable outcome (shelf renders, no bogus DELETE goes out), which
    // three layers cooperate to produce: LibraryPage's own try/catch around
    // the whole call (getOrCreateDeviceId() is an argument expression,
    // evaluated before .catch() is attached), revocation.ts's guard around
    // the callback, and the .catch() on reconcileOfflineCache itself. It
    // therefore does NOT single out any one of those; the guard inside
    // revocation's purge loop is pinned by revocation.test.ts instead.
    vi.spyOn(deviceIdModule, 'getOrCreateDeviceId').mockImplementation(() => {
      throw new Error('device id unavailable')
    })
    mockGet.mockResolvedValue({ data: { stories: [IN_PROGRESS] } })
    mockReconcile.mockImplementation((_profileId, _ids, options) => {
      options?.reportRemoval?.('s9')
      return Promise.resolve()
    })

    renderLibrary()

    expect(await screen.findByText('The Lantern')).toBeInTheDocument()
    expect(mockDelete).not.toHaveBeenCalled()
  })
})
