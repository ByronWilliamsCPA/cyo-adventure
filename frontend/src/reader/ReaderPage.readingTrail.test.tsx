import 'fake-indexeddb/auto'

import { IDBFactory } from 'fake-indexeddb'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ReadingTrailBatchBody } from '../client/types.gen'
import { _resetDbHandle } from '../offline/db'
import type { PutResponse, SyncApi } from '../offline/sync'
import type { ReadingState, Storybook } from '../player/types'
import { ReaderPage } from './ReaderPage'

// The reading-trail recorder rides on the shared axios instance ReaderPage
// builds via useApi(); a stable fake captures its POSTs (see
// ReaderPage.badgeToast.test.tsx for why the instance must be stable).
const postMock = vi.fn()
const getMock = vi.fn()
const fakeAxiosInstance = { get: getMock, post: postMock }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeAxiosInstance,
}))

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
    putReadingState: (_p, _s, body) =>
      Promise.resolve<PutResponse>({ status: 200, row: { ...body, state_revision: ++rev } }),
  }
}

// A resumed read sitting on the entrance, so the test drives real taps
// without depending on how a fresh read is introduced.
const SAVED: ReadingState = {
  current_node: 'n_entrance',
  var_state: { has_lantern: false },
  path: ['n_open', 'n_entrance'],
  visit_set: ['n_open', 'n_entrance'],
  version: 1,
  state_revision: 2,
  save_slots: {},
}

function trailSteps(): ReadingTrailBatchBody['steps'] {
  return postMock.mock.calls
    .filter((call) => String(call[0]).startsWith('/v1/reading-trail/'))
    .flatMap((call) => (call[1] as ReadingTrailBatchBody).steps)
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  vi.stubGlobal('scrollTo', vi.fn())
  getMock.mockReset()
  postMock.mockReset()
  getMock.mockRejectedValue(new Error('no progress in this test'))
  postMock.mockResolvedValue({ data: { recorded: true, stored_steps: 1 } })
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('ReaderPage reading trail', () => {
  it('records the taps of a resumed read through to its ending', async () => {
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          fetchServerState={() => Promise.resolve(SAVED)}
          profileId="p_trail"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
    fireEvent.click(await screen.findByTestId('choice-c_dark_passage'))
    await screen.findByTestId('ending-screen')
    await waitFor(() => expect(trailSteps().map((s) => s.kind)).toContain('end'))
    expect(trailSteps().map((s) => [s.kind, s.node_id, s.choice_id])).toEqual([
      ['resume', 'n_entrance', null],
      ['choice', 'n_entrance', 'c_take_lantern'],
      ['choice', 'n_cave_fork', 'c_dark_passage'],
      ['end', 'n_treasure', null],
    ])
    expect(postMock.mock.calls[0][0]).toBe('/v1/reading-trail/p_trail/s_lantern_cave')
  })

  it('keeps reading when every trail POST fails', async () => {
    postMock.mockRejectedValue(new Error('server down'))
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          fetchServerState={() => Promise.resolve(SAVED)}
          profileId="p_trail_failing"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
    fireEvent.click(await screen.findByTestId('choice-c_dark_passage'))
    expect(await screen.findByTestId('ending-screen')).toBeInTheDocument()
    expect(screen.queryByTestId('save-warning')).toBeNull()
  })
})
