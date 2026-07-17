import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { IDBFactory } from 'fake-indexeddb'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../notifications/ToastProvider'
import { _resetDbHandle, enqueueWrite, type QueuedWrite } from '../offline/db'
import type { ReadingState, Storybook } from '../player/types'
import { ReaderRoute } from './ReaderRoute'

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')
const lantern = (
  JSON.parse(readFileSync(tracesPath, 'utf-8')) as {
    traces: { story: Storybook }[]
  }
).traces[0].story

/**
 * Real axios rejections are `AxiosError` instances (an `Error` subclass); this
 * builds a real `Error` carrying the same shape axios attaches (`isAxiosError`,
 * `response`) so the mocked rejection is faithful to what the code under test
 * actually receives.
 */
function mockAxiosError(props: Record<string, unknown>): Error {
  return Object.assign(new Error('mock axios error'), props)
}

const mockGet = vi.fn()
const mockPut = vi.fn()
const mockPost = vi.fn()
// A single stable object, not a fresh literal per render: ReaderRoute memoizes
// syncApi/fetchStory/fetchServerState/recordCompletion via useMemo(..., [api]),
// so a fakeApi that changed identity across renders would defeat that
// memoization and mask the exact reload-loop regression the T5 test below
// guards against. Mirrors the pattern in LibraryPage.test.tsx / App.test.tsx.
const fakeApi = { get: mockGet, put: mockPut, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

// ToastProvider wraps the router in every render helper, mirroring App.tsx's
// production mounting: ReaderRoute calls useToast() unconditionally, so a
// bare render would throw its outside-provider error.
function renderAt(path: string) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/read/:profileId/:storybookId/:version" element={<ReaderRoute />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>
  )
}

// A route pattern missing a param the component expects, exercising the same
// "params are missing" guard a routing config mismatch would trigger for real.
function renderAtIncompleteRoute(path: string) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/read/:profileId" element={<ReaderRoute />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>
  )
}

describe('ReaderRoute guards', () => {
  it('shows a styled, exitable message for a non-integer version', () => {
    renderAt('/read/p1/s/abc')
    expect(screen.getByText('That story link looks wrong')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Back to my books' })).toBeTruthy()
  })

  it('refuses a story when a child session exists for a different profile (SEC-F1)', async () => {
    const { setChildSession, clearChildSession } = await import('../auth/childSession')
    setChildSession({ token: 't', expiresAt: '2099-01-01T00:00:00Z', profileId: 'p1' })
    try {
      // Session is for p1; deep-linking to p2's reader must be refused rather
      // than served from the offline cache.
      renderAt(`/read/p2/${lantern.id}/1`)
      expect(screen.getByText("That's not your bookshelf")).toBeTruthy()
    } finally {
      clearChildSession()
    }
  })

  it('shows a styled, exitable message when route params are missing', () => {
    renderAtIncompleteRoute('/read/p1')
    expect(screen.getByText("We couldn't tell which story to open")).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Back to start' })).toBeTruthy()
  })

  it('missing-params fallback navigates to the profile picker', async () => {
    render(
      <ToastProvider>
        <MemoryRouter initialEntries={['/read/p1']}>
          <Routes>
            <Route path="/read/:profileId" element={<ReaderRoute />} />
            <Route path="/kids" element={<div>picker-stub</div>} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Back to start' }))
    expect(await screen.findByText('picker-stub')).toBeTruthy()
  })
})

describe('ReaderRoute wiring (T5)', () => {
  beforeEach(() => {
    globalThis.indexedDB = new IDBFactory()
    _resetDbHandle()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPost.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('settles the reading-state endpoint to at most two calls through the real wired ports', async () => {
    // Regression for T5: fetchServerState/recordCompletion must be memoized
    // (useMemo keyed on the api instance) the same way syncApi/fetchStory
    // already are. A non-memoized `makeFetchServerState(api)` call inline in
    // the JSX would mint a fresh function identity every render, which sits
    // in ReaderPage's load() useCallback deps and would re-fire the mount
    // effect in an unbounded loop (the same failure mode covered for
    // ReaderPage's own default ports in ReaderPage.test.tsx's
    // "does not reload in a loop..." test, but exercised here through the
    // real route wiring instead of the NO_SERVER_STATE/NO_RECORD_COMPLETION
    // defaults).
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/v1/storybooks/')) {
        return Promise.resolve({ data: lantern })
      }
      if (url.startsWith('/v1/reading-state/')) {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 404 } }))
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    renderAt(`/read/p_t5/${lantern.id}/${lantern.version}`)

    await screen.findByTestId('reader')
    // Let the app settle; a reload loop would keep firing calls during this
    // window instead of going quiet after the initial load.
    await new Promise((resolve) => setTimeout(resolve, 400))

    const readingStateCalls = mockGet.mock.calls.filter(([url]) =>
      String(url).startsWith('/v1/reading-state/')
    )
    expect(readingStateCalls.length).toBeLessThanOrEqual(2)
  })

  it('applies a continuation seed parsed from router location state', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/v1/storybooks/')) {
        return Promise.resolve({ data: lantern })
      }
      if (url.startsWith('/v1/reading-state/')) {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 404 } }))
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    render(
      <ToastProvider>
        <MemoryRouter
          initialEntries={[
            {
              pathname: `/read/p_cont/${lantern.id}/${lantern.version}`,
              state: {
                continuation: { entryNode: 'n_cave_fork', varState: { has_lantern: true } },
              },
            },
          ]}
        >
          <Routes>
            <Route path="/read/:profileId/:storybookId/:version" element={<ReaderRoute />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    )

    await screen.findByTestId('reader')
    // The continuation seed jumps straight to n_cave_fork with has_lantern
    // carried in, so the gated choice is visible without clicking through
    // the start passage.
    expect(screen.getByTestId('passage-body').textContent).toContain('splits')
    expect(screen.getByTestId('choice-c_dark_passage')).toBeTruthy()
  })
})

describe('ReaderRoute replay reconciliation (B2)', () => {
  beforeEach(() => {
    globalThis.indexedDB = new IDBFactory()
    _resetDbHandle()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPost.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('shows the conflict dialog for a replayed 409 and resends the local device state on "keep this device"', async () => {
    const profileId = 'p_replay'
    const queuedState: ReadingState = {
      current_node: lantern.nodes[0].id,
      var_state: {},
      path: [lantern.nodes[0].id],
      visit_set: [lantern.nodes[0].id],
      version: lantern.version,
      state_revision: 1,
      save_slots: {},
    }
    const queuedWrite: QueuedWrite = {
      event_id: 'evt-replay-1',
      profile_id: profileId,
      storybook_id: lantern.id,
      base_revision: 1,
      state: queuedState,
      device_id: 'device-a',
      queued_at: Date.now(),
    }
    await enqueueWrite(queuedWrite)

    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/v1/storybooks/')) {
        return Promise.resolve({ data: lantern })
      }
      if (url.startsWith('/v1/reading-state/')) {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 404 } }))
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    const serverRow: ReadingState = { ...queuedState, state_revision: 2 }
    // ReaderPage's own live save (Reader reporting its initial position on
    // mount) races with the replay flush; both go through the same mocked
    // `put`. Distinguish by state_revision rather than call order: the queued
    // write (and its "keep this device" resend, which reuses the same
    // unrebased item.state) carry revision 1, ReaderPage's fresh live save
    // carries revision 0.
    let replayConflictSent = false
    mockPut.mockImplementation((_url: string, body: { state_revision: number }) => {
      if (body.state_revision === 1) {
        if (!replayConflictSent) {
          replayConflictSent = true
          return Promise.reject(
            mockAxiosError({
              isAxiosError: true,
              response: { status: 409, data: { current_row: serverRow } },
            })
          )
        }
        return Promise.resolve({ data: serverRow })
      }
      return Promise.resolve({ data: { ...body, state_revision: 1 } })
    })

    renderAt(`/read/${profileId}/${lantern.id}/${lantern.version}`)

    await screen.findByTestId('reader')
    await screen.findByTestId('conflict-dialog')

    // A conflicted replay is not "all caught up": the success toast must not
    // appear alongside (and contradict) the conflict dialog.
    expect(screen.queryByText('All caught up! Your reading is saved.')).toBeNull()

    function putBodies(): { current_node: string; state_revision: number }[] {
      return mockPut.mock.calls.map(
        (call) => call[1] as { current_node: string; state_revision: number }
      )
    }
    function replayBodies(): { current_node: string; state_revision: number }[] {
      return putBodies().filter((body) => body.state_revision === 1)
    }

    expect(replayBodies().length).toBe(1)

    fireEvent.click(screen.getByTestId('conflict-keep'))

    await waitFor(() => expect(replayBodies().length).toBe(2))
    expect(replayBodies()[1]).toMatchObject({ current_node: queuedState.current_node })

    await waitFor(() => expect(screen.queryByTestId('conflict-dialog')).toBeNull())
  })

  it('rebases and retries once when the resend itself conflicts, then clears the dialog on success', async () => {
    const profileId = 'p_replay_retry_ok'
    const queuedState: ReadingState = {
      current_node: lantern.nodes[0].id,
      var_state: {},
      path: [lantern.nodes[0].id],
      visit_set: [lantern.nodes[0].id],
      version: lantern.version,
      state_revision: 1,
      save_slots: {},
    }
    await enqueueWrite({
      event_id: 'evt-retry-ok-1',
      profile_id: profileId,
      storybook_id: lantern.id,
      base_revision: 1,
      state: queuedState,
      device_id: 'device-a',
      queued_at: Date.now(),
    })

    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/v1/storybooks/')) return Promise.resolve({ data: lantern })
      if (url.startsWith('/v1/reading-state/')) {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 404 } }))
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    // First conflict happens during B1's mount-time replay flush. The second
    // conflict happens on "keep this device"'s resend (still at revision 1,
    // the item's original base): a fresh concurrent edit landed while the
    // dialog was open, and the fix must rebase onto its currentRow (revision
    // 3) and retry once, which succeeds.
    const flushConflictRow: ReadingState = { ...queuedState, state_revision: 2 }
    const resendConflictRow: ReadingState = { ...queuedState, state_revision: 3 }
    let revision1Calls = 0
    mockPut.mockImplementation((_url: string, body: { state_revision: number }) => {
      if (body.state_revision === 1) {
        revision1Calls += 1
        const currentRow = revision1Calls === 1 ? flushConflictRow : resendConflictRow
        return Promise.reject(
          mockAxiosError({
            isAxiosError: true,
            response: { status: 409, data: { current_row: currentRow } },
          })
        )
      }
      if (body.state_revision === 3) {
        return Promise.resolve({ data: { ...body, state_revision: 3 } as ReadingState })
      }
      return Promise.resolve({ data: { ...body, state_revision: 1 } as ReadingState })
    })

    renderAt(`/read/${profileId}/${lantern.id}/${lantern.version}`)

    await screen.findByTestId('reader')
    await screen.findByTestId('conflict-dialog')

    fireEvent.click(screen.getByTestId('conflict-keep'))

    await waitFor(() => expect(revision1Calls).toBe(2))
    await waitFor(() =>
      expect(
        mockPut.mock.calls.some(
          (call) => (call[1] as { state_revision: number }).state_revision === 3
        )
      ).toBe(true)
    )
    await waitFor(() => expect(screen.queryByTestId('conflict-dialog')).toBeNull())
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('keeps the dialog open for a story whose resend conflicts again even after the rebased retry', async () => {
    const profileId = 'p_replay_retry_conflict'
    const queuedState: ReadingState = {
      current_node: lantern.nodes[0].id,
      var_state: {},
      path: [lantern.nodes[0].id],
      visit_set: [lantern.nodes[0].id],
      version: lantern.version,
      state_revision: 1,
      save_slots: {},
    }
    await enqueueWrite({
      event_id: 'evt-retry-conflict-1',
      profile_id: profileId,
      storybook_id: lantern.id,
      base_revision: 1,
      state: queuedState,
      device_id: 'device-a',
      queued_at: Date.now(),
    })

    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/v1/storybooks/')) return Promise.resolve({ data: lantern })
      if (url.startsWith('/v1/reading-state/')) {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 404 } }))
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    const flushConflictRow: ReadingState = { ...queuedState, state_revision: 2 }
    const resendConflictRow: ReadingState = { ...queuedState, state_revision: 3 }
    const retryConflictRow: ReadingState = { ...queuedState, state_revision: 4 }
    let revision1Calls = 0
    mockPut.mockImplementation((_url: string, body: { state_revision: number }) => {
      if (body.state_revision === 1) {
        revision1Calls += 1
        const currentRow = revision1Calls === 1 ? flushConflictRow : resendConflictRow
        return Promise.reject(
          mockAxiosError({
            isAxiosError: true,
            response: { status: 409, data: { current_row: currentRow } },
          })
        )
      }
      if (body.state_revision === 3) {
        // The rebased retry conflicts again: a second concurrent edit landed.
        return Promise.reject(
          mockAxiosError({
            isAxiosError: true,
            response: { status: 409, data: { current_row: retryConflictRow } },
          })
        )
      }
      return Promise.resolve({ data: { ...body, state_revision: 1 } as ReadingState })
    })

    renderAt(`/read/${profileId}/${lantern.id}/${lantern.version}`)

    await screen.findByTestId('reader')
    await screen.findByTestId('conflict-dialog')

    fireEvent.click(screen.getByTestId('conflict-keep'))

    await waitFor(() => expect(revision1Calls).toBe(2))
    await waitFor(() =>
      expect(
        mockPut.mock.calls.some(
          (call) => (call[1] as { state_revision: number }).state_revision === 3
        )
      ).toBe(true)
    )
    // The story re-conflicted after the single allowed retry: the dialog must
    // stay open for this story rather than being blanket-cleared, and no
    // failure banner should appear (this is an unresolved conflict, not a
    // dropped write).
    expect(screen.getByTestId('conflict-dialog')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('counts a thrown resend error toward the failed-progress banner instead of an unhandled rejection', async () => {
    const profileId = 'p_replay_resend_throws'
    const queuedState: ReadingState = {
      current_node: lantern.nodes[0].id,
      var_state: {},
      path: [lantern.nodes[0].id],
      visit_set: [lantern.nodes[0].id],
      version: lantern.version,
      state_revision: 1,
      save_slots: {},
    }
    await enqueueWrite({
      event_id: 'evt-resend-throws-1',
      profile_id: profileId,
      storybook_id: lantern.id,
      base_revision: 1,
      state: queuedState,
      device_id: 'device-a',
      queued_at: Date.now(),
    })

    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/v1/storybooks/')) return Promise.resolve({ data: lantern })
      if (url.startsWith('/v1/reading-state/')) {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 404 } }))
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    const flushConflictRow: ReadingState = { ...queuedState, state_revision: 2 }
    let revision1Calls = 0
    mockPut.mockImplementation((_url: string, body: { state_revision: number }) => {
      if (body.state_revision === 1) {
        revision1Calls += 1
        if (revision1Calls === 1) {
          return Promise.reject(
            mockAxiosError({
              isAxiosError: true,
              response: { status: 409, data: { current_row: flushConflictRow } },
            })
          )
        }
        // The resend itself fails outright (a real HTTP error, not a 409 and
        // not a transport failure): saveProgress must propagate this rather
        // than queue it, and resolveKeepThisDevice must catch it per story.
        return Promise.reject(
          mockAxiosError({ isAxiosError: true, response: { status: 500, data: {} } })
        )
      }
      return Promise.resolve({ data: { ...body, state_revision: 1 } as ReadingState })
    })

    let unhandledRejection: unknown
    function onUnhandledRejection(event: PromiseRejectionEvent): void {
      unhandledRejection = event.reason
    }
    window.addEventListener('unhandledrejection', onUnhandledRejection)

    renderAt(`/read/${profileId}/${lantern.id}/${lantern.version}`)

    await screen.findByTestId('reader')
    await screen.findByTestId('conflict-dialog')

    fireEvent.click(screen.getByTestId('conflict-keep'))

    await waitFor(() => expect(revision1Calls).toBe(2))
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(screen.getByRole('alert').textContent).toContain(
      "We couldn't save some of your reading."
    )
    // The banner's only control reads "OK", not "Dismiss": young kids read it.
    expect(screen.getByRole('button', { name: 'OK' })).toBeTruthy()

    window.removeEventListener('unhandledrejection', onUnhandledRejection)
    expect(unhandledRejection).toBeUndefined()
  })
})

describe('ReaderRoute replay success toast', () => {
  beforeEach(() => {
    globalThis.indexedDB = new IDBFactory()
    _resetDbHandle()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPost.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('shows a kid-safe success toast when a reconnect replay lands cleanly', async () => {
    const profileId = 'p_replay_success'
    const queuedState: ReadingState = {
      current_node: lantern.nodes[0].id,
      var_state: {},
      path: [lantern.nodes[0].id],
      visit_set: [lantern.nodes[0].id],
      version: lantern.version,
      state_revision: 1,
      save_slots: {},
    }
    await enqueueWrite({
      event_id: 'evt-replay-success-1',
      profile_id: profileId,
      storybook_id: lantern.id,
      base_revision: 1,
      state: queuedState,
      device_id: 'device-a',
      queued_at: Date.now(),
    })

    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/v1/storybooks/')) return Promise.resolve({ data: lantern })
      if (url.startsWith('/v1/reading-state/')) {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 404 } }))
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    // Every save succeeds: the mount-time flush replays the queued write
    // (revision 1) cleanly, giving replayed > 0 with no conflicts and no
    // failures. ReaderPage's own live save (revision 0) shares this mock but
    // has no bearing on the replay outcome.
    mockPut.mockImplementation((_url: string, body: { state_revision: number }) =>
      Promise.resolve({ data: { ...body, state_revision: body.state_revision + 1 } })
    )

    renderAt(`/read/${profileId}/${lantern.id}/${lantern.version}`)

    await screen.findByTestId('reader')
    expect(await screen.findByText('All caught up! Your reading is saved.')).toBeTruthy()
    // Success means success: neither failure surface is up beside the toast.
    expect(screen.queryByTestId('conflict-dialog')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()

    // The kid-readable manual dismissal: "OK" clears it without waiting for
    // the auto-dismiss window.
    fireEvent.click(screen.getByRole('button', { name: 'OK' }))
    expect(screen.queryByText('All caught up! Your reading is saved.')).toBeNull()
  })
})
