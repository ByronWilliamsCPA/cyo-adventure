/**
 * Leave-button semantics around in-flight progress saves.
 *
 * persist() is fired-and-forgotten on every choice and its lost-save warning
 * renders inside ReaderPage's own tree; navigating away on Leave used to
 * unmount the page and silently swallow the warning of a save that failed
 * after the tap. These tests pin the fix: Leave settles the pending save
 * (bounded), holds the first tap when the save was lost so the warning is
 * seen, and always leaves on the next tap.
 */

import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as db from '../offline/db'
import { _resetDbHandle } from '../offline/db'
import type { PutResponse, SyncApi } from '../offline/sync'
import type { Storybook } from '../player/types'
import { Reader } from './Reader'
import { ReaderPage } from './ReaderPage'

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')
const lantern = (
  JSON.parse(readFileSync(tracesPath, 'utf-8')) as {
    traces: { story: Storybook }[]
  }
).traces[0].story

function okApi(): SyncApi {
  let rev = 0
  return {
    putReadingState: (_p, _s, _b) =>
      Promise.resolve<PutResponse>({
        status: 200,
        row: { ..._b, state_revision: ++rev },
      }),
  }
}

function renderReaderPage(api = okApi()) {
  return render(
    <MemoryRouter initialEntries={['/read/p_leave/s_lantern_cave/1']}>
      <Routes>
        <Route
          path="/read/:profileId/:storybookId/:version"
          element={
            <ReaderPage
              api={api}
              fetchStory={() => Promise.resolve(lantern)}
              profileId="p_leave"
              storybookId="s_lantern_cave"
              version={1}
            />
          }
        />
        <Route path="/library/:profileId" element={<div>Library Page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('ReaderPage Leave with an in-flight save', () => {
  it('surfaces a lost save and blocks the first Leave tap; a second tap still leaves', async () => {
    // The mount-time save's local write hangs until this test rejects it,
    // simulating a save that is still in flight when the child taps Leave and
    // then fails (LocalWriteError -> the 'lost' warning; see offline/sync.ts).
    let rejectWrite: ((reason: Error) => void) | undefined
    vi.spyOn(db, 'putReadingState').mockImplementation(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectWrite = reject
        })
    )
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    renderReaderPage()
    await screen.findByTestId('reader')
    await waitFor(() => expect(rejectWrite).toBeDefined())

    // First tap: the save is still pending, so Leave waits for it.
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }))
    rejectWrite?.(new Error('quota exceeded'))

    // The failure surfaces and this tap does NOT navigate: the page (and its
    // role="alert" banner) must stay mounted so the loss is actually seen.
    expect(await screen.findByTestId('save-warning')).toHaveTextContent(
      "We couldn't save your last step."
    )
    expect(screen.queryByText('Library Page')).toBeNull()
    expect(screen.getByTestId('reader')).toBeTruthy()

    // Second tap: leaves regardless, so the child is never stuck.
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }))
    expect(await screen.findByText('Library Page')).toBeTruthy()
  })

  it('navigates to the library immediately when no save is pending or at risk', async () => {
    renderReaderPage()
    await screen.findByTestId('reader')
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }))
    expect(await screen.findByText('Library Page')).toBeTruthy()
  })
})

describe('Reader Leave button contract', () => {
  it('falls back to navigating to the library when onLeave is not provided', () => {
    render(
      <MemoryRouter initialEntries={['/read/p1/s/1']}>
        <Routes>
          <Route
            path="/read/:profileId/:storybookId/:version"
            element={<Reader story={lantern} profileId="p1" />}
          />
          <Route path="/library/:profileId" element={<div>Library Page</div>} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }))
    expect(screen.getByText('Library Page')).toBeTruthy()
  })

  it('invokes onLeave instead of navigating when provided', () => {
    const onLeave = vi.fn()
    render(
      <MemoryRouter initialEntries={['/read/p1/s/1']}>
        <Routes>
          <Route
            path="/read/:profileId/:storybookId/:version"
            element={<Reader story={lantern} profileId="p1" onLeave={onLeave} />}
          />
          <Route path="/library/:profileId" element={<div>Library Page</div>} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }))
    expect(onLeave).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Library Page')).toBeNull()
  })
})
