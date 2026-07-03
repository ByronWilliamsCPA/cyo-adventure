import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { _resetDbHandle, putReadingState } from '../offline/db'
import type { PutResponse, SyncApi } from '../offline/sync'
import type { ReadingState, Storybook } from '../player/types'
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

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
})
afterEach(cleanup)

describe('ReaderPage', () => {
  it('fetches and caches the story, then plays it to an ending', async () => {
    const fetchStory = vi.fn(() => Promise.resolve(lantern))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={fetchStory}
          profileId="p_play"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(fetchStory).toHaveBeenCalledOnce()
    // Use findBy* after each interaction: a choice/ending can render a tick
    // later than the click, so synchronous getBy* races under coverage timing.
    fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
    fireEvent.click(await screen.findByTestId('choice-c_dark_passage'))
    expect(await screen.findByTestId('ending-screen')).toBeTruthy()
    expect(screen.getByTestId('ending-id').textContent).toBe('e_treasure_found')
  })

  it('resumes from saved reading state', async () => {
    const saved: ReadingState = {
      current_node: 'n_cave_fork',
      var_state: { has_lantern: true },
      path: ['n_entrance', 'n_cave_fork'],
      visit_set: ['n_entrance', 'n_cave_fork'],
      version: 1,
      state_revision: 3,
      save_slots: {},
    }
    await putReadingState('p1', 's_lantern_cave', saved)
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p1"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(screen.getByTestId('passage-body').textContent).toContain('splits')
    // The lantern was already taken, so the conditional choice is visible.
    expect(screen.getByTestId('choice-c_dark_passage')).toBeTruthy()
  })

  it('shows download-needed when offline with no cached story', async () => {
    const fetchStory = vi.fn(() => Promise.reject(new Error('offline')))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={fetchStory}
          profileId="p_dl"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('download-needed')
  })

  it('surfaces the conflict dialog on a 409 and resolves it', async () => {
    let calls = 0
    const api: SyncApi = {
      putReadingState: (_p, _s, body) => {
        calls += 1
        if (calls === 1) {
          return Promise.resolve<PutResponse>({
            status: 409,
            currentRow: {
              ...body,
              current_node: 'n_cave_fork',
              state_revision: 5,
            },
          })
        }
        return Promise.resolve<PutResponse>({
          status: 200,
          row: { ...body, state_revision: 6 },
        })
      },
    }
    render(
      <MemoryRouter>
        <ReaderPage
          api={api}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_conf"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    // The initial save (on mount) returns 409, so the dialog appears.
    await screen.findByTestId('conflict-dialog')
    fireEvent.click(screen.getByTestId('conflict-keep'))
    await waitFor(() => expect(screen.queryByTestId('conflict-dialog')).toBeNull())
  })
})
