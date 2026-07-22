import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { IDBFactory } from 'fake-indexeddb'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../notifications/ToastProvider'
import { _resetDbHandle, enqueueWrite } from '../offline/db'
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

  it('silently discards a replayed 409 without showing a conflict dialog', async () => {
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
    await enqueueWrite({
      event_id: 'evt-replay-1',
      profile_id: profileId,
      storybook_id: lantern.id,
      base_revision: 1,
      state: queuedState,
      device_id: 'device-a',
      queued_at: Date.now(),
    })

    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/v1/storybooks/')) {
        return Promise.resolve({ data: lantern })
      }
      if (url.startsWith('/v1/reading-state/')) {
        return Promise.reject(mockAxiosError({ isAxiosError: true, response: { status: 404 } }))
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    // The queued write (revision 1) 409s during the mount-time replay flush;
    // ReaderPage's own live save (revision 0) succeeds. Newest-write-wins: the
    // held write is silently discarded, so no dialog, no banner, and no success
    // toast (a conflict suppresses the toast) ever appear. Distinguish the two
    // saves by state_revision, not call order.
    const serverRow: ReadingState = { ...queuedState, state_revision: 2 }
    mockPut.mockImplementation((_url: string, body: { state_revision: number }) => {
      if (body.state_revision === 1) {
        return Promise.reject(
          mockAxiosError({
            isAxiosError: true,
            response: { status: 409, data: { current_row: serverRow } },
          })
        )
      }
      return Promise.resolve({ data: { ...body, state_revision: 1 } })
    })

    renderAt(`/read/${profileId}/${lantern.id}/${lantern.version}`)

    await screen.findByTestId('reader')

    function replayBodies(): { state_revision: number }[] {
      return mockPut.mock.calls
        .map((call) => call[1] as { state_revision: number })
        .filter((body) => body.state_revision === 1)
    }
    // The replay attempt reached the server (and 409'd) exactly once; it is
    // never resent, because newest-write-wins discards it instead of offering
    // a "keep this device" resend.
    await waitFor(() => expect(replayBodies().length).toBe(1))

    // Give any (incorrect) dialog or resend a chance to appear before asserting
    // their absence.
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(replayBodies().length).toBe(1)
    expect(screen.queryByTestId('conflict-dialog')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText('All caught up! Your reading is saved.')).toBeNull()
  })

  it('surfaces the ask-a-grown-up banner when a replayed write fails outright', async () => {
    const profileId = 'p_replay_failed'
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
      event_id: 'evt-replay-failed-1',
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

    // The queued write (revision 1) fails with a non-offline server error, so
    // replayQueue drops it and reports it in outcome.failed; ReaderPage's own
    // live save (revision 0) succeeds. A genuine failure is NOT silently
    // discarded like a conflict: it still defers to a grown-up via the banner.
    mockPut.mockImplementation((_url: string, body: { state_revision: number }) => {
      if (body.state_revision === 1) {
        return Promise.reject(
          mockAxiosError({ isAxiosError: true, response: { status: 500, data: {} } })
        )
      }
      return Promise.resolve({ data: { ...body, state_revision: 1 } })
    })

    renderAt(`/read/${profileId}/${lantern.id}/${lantern.version}`)

    await screen.findByTestId('reader')
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(screen.getByRole('alert').textContent).toContain(
      "We couldn't save some of your reading."
    )
    // The banner's only control reads "OK", not "Dismiss": young kids read it.
    expect(screen.getByRole('button', { name: 'OK' })).toBeTruthy()
    // A failure is not a conflict: no dialog appears.
    expect(screen.queryByTestId('conflict-dialog')).toBeNull()
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
