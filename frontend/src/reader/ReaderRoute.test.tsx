import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { IDBFactory } from 'fake-indexeddb'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { _resetDbHandle } from '../offline/db'
import type { Storybook } from '../player/types'
import { ReaderRoute } from './ReaderRoute'

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')
const lantern = (
  JSON.parse(readFileSync(tracesPath, 'utf-8')) as {
    traces: { story: Storybook }[]
  }
).traces[0].story

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

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/read/:profileId/:storybookId/:version" element={<ReaderRoute />} />
      </Routes>
    </MemoryRouter>
  )
}

// A route pattern missing a param the component expects, exercising the same
// "params are missing" guard a routing config mismatch would trigger for real.
function renderAtIncompleteRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/read/:profileId" element={<ReaderRoute />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('ReaderRoute guards', () => {
  it('shows a styled, exitable message for a non-integer version', () => {
    renderAt('/read/p1/s/abc')
    expect(screen.getByText('That story link looks wrong')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Back to my books' })).toBeTruthy()
  })

  it('shows a styled, exitable message when route params are missing', () => {
    renderAtIncompleteRoute('/read/p1')
    expect(screen.getByText("We couldn't tell which story to open")).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Back to start' })).toBeTruthy()
  })

  it('missing-params fallback navigates to the profile picker', async () => {
    render(
      <MemoryRouter initialEntries={['/read/p1']}>
        <Routes>
          <Route path="/read/:profileId" element={<ReaderRoute />} />
          <Route path="/kids" element={<div>picker-stub</div>} />
        </Routes>
      </MemoryRouter>
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
        return Promise.reject({ isAxiosError: true, response: { status: 404 } })
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
})
