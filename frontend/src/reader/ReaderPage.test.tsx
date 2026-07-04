import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ForbiddenError, StoryNotFoundError } from '../api/readerApi'
import * as db from '../offline/db'
import { _resetDbHandle, putReadingState } from '../offline/db'
import type { PutResponse, SyncApi } from '../offline/sync'
import { OfflineError } from '../offline/sync'
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

function renderPage(fetchStory: (id: string, v: number) => Promise<Storybook>, api = okApi()) {
  return render(
    <MemoryRouter>
      <ReaderPage api={api} fetchStory={fetchStory} profileId="p1" storybookId="s" version={1} />
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

  it('falls back to the network fetch when reading the local cache throws', async () => {
    vi.spyOn(db, 'getCachedStorybook').mockRejectedValueOnce(new Error('DB blocked'))
    const fetchStory = vi.fn(() => Promise.resolve(lantern))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={fetchStory}
          profileId="p_dbdown"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(fetchStory).toHaveBeenCalledOnce()
  })

  it('still reaches reading when caching the fetched story locally fails', async () => {
    vi.spyOn(db, 'cacheStorybook').mockRejectedValueOnce(new Error('quota exceeded'))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_cachefail"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
  })

  it('starts fresh instead of blocking when reading the local reading-state throws', async () => {
    vi.spyOn(db, 'getReadingState').mockRejectedValueOnce(new Error('DB blocked'))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_statedown"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
  })

  it('shows download-needed when offline with no cached story', async () => {
    const fetchStory = vi.fn(() => Promise.reject(new OfflineError()))
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

  it('shows a not-found screen when the story does not exist', async () => {
    renderPage(() => Promise.reject(new StoryNotFoundError()))
    expect(await screen.findByText("We couldn't find that story")).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Back to my books' })).toBeTruthy()
  })

  it('shows the offline screen on a transport failure', async () => {
    renderPage(() => Promise.reject(new OfflineError()))
    expect(await screen.findByTestId('download-needed')).toBeTruthy()
  })

  it('shows a generic error screen on other failures', async () => {
    renderPage(() => Promise.reject(new Error('boom')))
    expect(await screen.findByText('Something went wrong')).toBeTruthy()
  })

  it('shows a forbidden screen on a 403, with no retry that could never succeed', async () => {
    renderPage(() => Promise.reject(new ForbiddenError()))
    expect(await screen.findByText("You don't have access to this story")).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Back to my books' })).toBeTruthy()
  })

  it('warns immediately when a save is lost locally, not just server-side', async () => {
    vi.spyOn(db, 'putReadingState').mockRejectedValueOnce(new Error('quota exceeded'))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_lost"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    // The mount-time save (Reader's initial progress report) hits the mocked
    // rejection; a single local-write failure is real loss, so it must not
    // wait for a second occurrence before surfacing.
    expect(await screen.findByTestId('save-warning')).toHaveTextContent(
      "couldn't save that step"
    )
  })

  it('warns after repeated remote save failures but not after just one', async () => {
    const api: SyncApi = {
      putReadingState: () => Promise.reject(new Error('500 server error')),
    }
    render(
      <MemoryRouter>
        <ReaderPage
          api={api}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_failing"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    // The mount-time save is the first failure; a single blip is not yet
    // surfaced.
    await screen.findByTestId('reader')
    await waitFor(() => expect(screen.queryByTestId('save-warning')).toBeNull())
    // A second, consecutive failure (from the next progress report) crosses
    // the threshold.
    fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
    expect(await screen.findByTestId('save-warning')).toHaveTextContent(
      'trouble saving your progress'
    )
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

  it('issues one save and no false 409 under StrictMode double-invoke (#86)', async () => {
    let calls = 0
    const api: SyncApi = {
      putReadingState: (_p, _s, body) => {
        calls += 1
        // The server would 409 a second identical save at the same base revision;
        // if the client dedupes the StrictMode double-fire, calls stays at 1.
        if (calls === 1) {
          return Promise.resolve<PutResponse>({ status: 200, row: { ...body, state_revision: 1 } })
        }
        return Promise.resolve<PutResponse>({
          status: 409,
          currentRow: { ...body, state_revision: 1 },
        })
      },
    }
    render(
      <StrictMode>
        <MemoryRouter>
          <ReaderPage
            api={api}
            fetchStory={() => Promise.resolve(lantern)}
            profileId="p_strict"
            storybookId="s_lantern_cave"
            version={1}
          />
        </MemoryRouter>
      </StrictMode>
    )
    await screen.findByTestId('reader')
    // Let any second effect-fire flush.
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(1))
    expect(calls).toBe(1)
    expect(screen.queryByTestId('conflict-dialog')).toBeNull()
  })
})
