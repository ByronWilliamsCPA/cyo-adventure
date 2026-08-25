import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ForbiddenError, StoryNotFoundError, UnauthenticatedError } from '../api/readerApi'
import * as db from '../offline/db'
import { _resetDbHandle, getReadingState, putReadingState } from '../offline/db'
import type { PutResponse, SyncApi } from '../offline/sync'
import { OfflineError } from '../offline/sync'
import type { ValuesPayload } from '../player/personalization'
import type { ContinuationSeed } from '../player/series'
import type { ReadingState, Storybook, VarState } from '../player/types'
import type { CharacterBinding } from './characterSeed'
import { deriveCharacterSeed } from './characterSeed'
import { ReaderPage } from './ReaderPage'

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')
const lantern = (
  JSON.parse(readFileSync(tracesPath, 'utf-8')) as {
    traces: { story: Storybook }[]
  }
).traces[0].story

// A minimal fixture (mirrors Reader.test.tsx's sentinelStory) whose body
// carries an ADR-023 sentinel, for the C3d personalization-wiring tests. No
// choices: these tests only need the start passage to render.
const sentinelStory: Storybook = {
  schema_version: '2.0',
  id: 's_sentinel',
  version: 1,
  title: 'Sentinel',
  metadata: {},
  variables: [],
  start_node: 'n_start',
  nodes: [
    {
      id: 'n_start',
      body: 'Then {~HERO:Explorer~} ran.',
      is_ending: false,
      choices: [],
    },
  ],
}

// ADR-028 Task 9: a minimal fixture with one declared bool variable and a
// choice gated on it, so a carried character seed (`has_sword: true`)
// produces an observably different set of visible choices than an unseeded
// start (`has_sword` defaults to false). Used to prove the seed genuinely
// reaches the machine, not just that a prop was threaded somewhere.
const seedStory: Storybook = {
  schema_version: '2.0',
  id: 's_seed',
  version: 1,
  title: 'Seed Test',
  metadata: {},
  variables: [{ name: 'has_sword', type: 'bool', initial: false }],
  start_node: 'n_gate',
  nodes: [
    {
      id: 'n_gate',
      body: 'You stand at the gate.',
      is_ending: false,
      choices: [
        {
          id: 'c_sword',
          label: 'Draw your sword',
          target: 'n_gate_end',
          condition: { var: 'has_sword' },
        },
        { id: 'c_plain', label: 'Walk on', target: 'n_gate_end' },
      ],
    },
    {
      id: 'n_gate_end',
      body: 'The end.',
      is_ending: true,
      choices: [],
      ending: { id: 'e_gate', kind: 'completion', valence: 'neutral', title: 'Done' },
    },
  ],
}

/**
 * A ReadingState-typed value that, at runtime, actually carries the two
 * Task 6/ADR-028 View-only fields the reader needs (`character_name`,
 * `seed_var_state`), mirroring sync.test.ts's own `viewShapedState`
 * precedent for a server View cached under a `ReadingState`-typed binding
 * (both the local IndexedDB cache and `fetchServerState` are typed
 * `ReadingState` but carry a real `ReadingStateView` at runtime).
 */
function withCharacterSeed(
  state: ReadingState,
  characterName: string | null,
  seedVarState: VarState | null
): ReadingState {
  return {
    ...state,
    character_name: characterName,
    seed_var_state: seedVarState,
  } as unknown as ReadingState
}

function valuesPayload(): ValuesPayload {
  return {
    subject_profile_id: 'p_1',
    ring: 1,
    policy_version: 'ring1-no-consent-required',
    resolved_at: '2026-07-29T00:00:00Z',
    values: { protagonist_first_name: 'Maya' },
    sentinel_pattern: "\\{~([A-Z][A-Z0-9_]*):([^{}<>'~]+)~\\}",
    slot_bindings: { HERO: 'protagonist_first_name' },
  }
}

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
  // jsdom's window.scrollTo exists but only logs "Not implemented"; the
  // Reader scrolls on every passage change, so stub it to keep tests quiet.
  vi.stubGlobal('scrollTo', vi.fn())
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('ReaderPage', () => {
  it('shows the branded loading state while the story is being opened', () => {
    // A fetch that never settles keeps the page in its loading phase.
    renderPage(() => new Promise<Storybook>(() => {}))
    const loading = screen.getByTestId('loading')
    expect(loading).toHaveTextContent('Opening your story…')
    expect(loading.getAttribute('role')).toBe('status')
  })

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

  it('does not report a download when caching failed', async () => {
    vi.spyOn(db, 'cacheStorybook').mockRejectedValueOnce(new Error('quota exceeded'))
    const reportDownload = vi.fn()
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_cachefail_report"
          storybookId="s_lantern_cave"
          version={1}
          reportDownload={reportDownload}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    // isCachedLocally only ever becomes true from a cache HIT or a cache
    // write that actually succeeded; a rejected cacheStorybook must leave it
    // false, so reportDownload (gated on isCachedLocally) must never fire.
    expect(reportDownload).not.toHaveBeenCalled()
  })

  it('reports a download once when caching the fetched story succeeds', async () => {
    const reportDownload = vi.fn()
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_cacheok_report"
          storybookId="s_lantern_cave"
          version={1}
          reportDownload={reportDownload}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(reportDownload).toHaveBeenCalledOnce()
    expect(reportDownload).toHaveBeenCalledWith('s_lantern_cave')
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

  it("navigates to the profile library from the offline screen's Back to my books button", async () => {
    render(
      <MemoryRouter initialEntries={['/read/p_dl/s_lantern_cave/1']}>
        <Routes>
          <Route
            path="/read/:profileId/:storybookId/:version"
            element={
              <ReaderPage
                api={okApi()}
                fetchStory={() => Promise.reject(new OfflineError())}
                profileId="p_dl"
                storybookId="s_lantern_cave"
                version={1}
              />
            }
          />
          <Route path="/library/:profileId" element={<div>Library Page</div>} />
        </Routes>
      </MemoryRouter>
    )
    await screen.findByTestId('download-needed')
    fireEvent.click(screen.getByTestId('download-back'))
    expect(await screen.findByText('Library Page')).toBeInTheDocument()
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

  it('shows the ask-a-grown-up gate on a 401 during load, with no retry', async () => {
    renderPage(() => Promise.reject(new UnauthenticatedError()))
    expect(await screen.findByText('Ask a grown-up to help')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'I am a grown-up' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })

  it('shows the ask-a-grown-up gate and stops saving when a save 401s', async () => {
    // The story loads fine (from cache/network), but the child token expires
    // mid-read: the mount-time save 401s. That must surface the gate, not the
    // misleading "we'll keep trying" save banner.
    const putReadingState = vi.fn(() => Promise.reject(new UnauthenticatedError()))
    const api: SyncApi = { putReadingState }
    render(
      <MemoryRouter>
        <ReaderPage
          api={api}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_expired"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    expect(await screen.findByText('Ask a grown-up to help')).toBeTruthy()
    expect(screen.queryByTestId('save-warning')).toBeNull()
    // The reader is torn down, so no further choices (hence no further saves)
    // can fire once the gate is shown.
    expect(screen.queryByTestId('reader')).toBeNull()
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
    const warning = await screen.findByTestId('save-warning')
    expect(warning).toHaveTextContent("We couldn't save your last step.")
    expect(warning).toHaveTextContent(
      'Your story will keep going, but that step might not be remembered.'
    )
    expect(warning).toHaveTextContent('Ask a grown-up if this keeps happening.')
    // The step is stored nowhere and nothing ever retries it (see persist's
    // LocalWriteError branch), so the banner must not borrow the transient
    // state's retry promise.
    expect(warning).not.toHaveTextContent('keep trying')
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
    // the threshold. Unlike the 'lost' banner, this one may promise a retry:
    // every next choice really does attempt another save.
    fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
    const warning = await screen.findByTestId('save-warning')
    expect(warning).toHaveTextContent(
      "We're having trouble saving your progress. Keep reading; we'll keep trying."
    )
    expect(warning).not.toHaveTextContent('might not be remembered')
  })

  it('replaces the transient retry banner with the honest lost copy on a local write failure', async () => {
    // Remote saves always fail, so the transient 'failing' banner appears
    // first; then a local write failure means a step is stored nowhere at
    // all, which must swap in the honest permanent-loss copy rather than
    // keep promising a retry that will never happen.
    const api: SyncApi = {
      putReadingState: () => Promise.reject(new Error('500 server error')),
    }
    render(
      <MemoryRouter>
        <ReaderPage
          api={api}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_failing_then_lost"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    // Second consecutive remote failure surfaces the transient banner.
    fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
    expect(await screen.findByTestId('save-warning')).toHaveTextContent("we'll keep trying")
    // The next step's local write fails: this step is lost for real.
    vi.spyOn(db, 'putReadingState').mockRejectedValueOnce(new Error('quota exceeded'))
    fireEvent.click(await screen.findByTestId('choice-c_dark_passage'))
    await waitFor(() => {
      const warning = screen.getByTestId('save-warning')
      expect(warning).toHaveTextContent("We couldn't save your last step.")
      expect(warning).not.toHaveTextContent('keep trying')
    })
  })

  it('silently adopts the server position on a 409 without showing a dialog', async () => {
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
    // The initial save (on mount) 409s. Newest-write-wins: the reader silently
    // adopts the server row (the cave fork) and keeps reading; no conflict
    // dialog is ever shown to the child.
    await waitFor(() => expect(screen.getByTestId('passage-body').textContent).toContain('splits'))
    expect(screen.queryByTestId('conflict-dialog')).toBeNull()
  })

  it('silently adopts the server var_state and position on a 409', async () => {
    const serverState: ReadingState = {
      current_node: 'n_cave_fork',
      var_state: { has_lantern: true },
      path: ['n_entrance', 'n_cave_fork'],
      visit_set: ['n_entrance', 'n_cave_fork'],
      version: 1,
      state_revision: 5,
      save_slots: {},
    }
    let calls = 0
    const api: SyncApi = {
      putReadingState: (_p, _s, body) => {
        calls += 1
        if (calls === 1) {
          return Promise.resolve<PutResponse>({ status: 409, currentRow: serverState })
        }
        return Promise.resolve<PutResponse>({ status: 200, row: { ...body, state_revision: 6 } })
      },
    }
    render(
      <MemoryRouter>
        <ReaderPage
          api={api}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_adopt"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    // The mount-time save 409s (another device is ahead). No dialog is shown:
    // the Reader silently remounts seeded from the adopted server state, so the
    // fork passage renders, and the lantern-gated choice is visible because the
    // server's var_state (has_lantern: true) was adopted too.
    await waitFor(() => expect(screen.getByTestId('passage-body').textContent).toContain('splits'))
    expect(screen.queryByTestId('conflict-dialog')).toBeNull()
    expect(screen.getByTestId('choice-c_dark_passage')).toBeTruthy()

    // The adopted state was mirrored into the local cache so the next open
    // resumes from the server position (resolveConflict's use_newer_progress
    // path). The remounted Reader immediately re-saves the adopted state, so
    // the stored revision may already have advanced past the server's 5; the
    // position, not the exact revision, is the adopted-state invariant.
    //
    // Retried for the same async-persist reason as the two continuation-seed
    // reads below. Correcting the reasoning recorded when those were fixed:
    // this is the THIRD sibling read, not one of "two that both pre-seed their
    // row". `p_adopt` is never passed to putReadingState, so this row starts
    // nonexistent locally and can read back `undefined` exactly like they can.
    // It has only been getting away with it: the render awaited above happens
    // after resolveConflict initiates the mirror write, which buys a longer
    // head start on the same race rather than immunity to it.
    await waitFor(async () => {
      const mirrored = await getReadingState('p_adopt', 's_lantern_cave')
      expect(mirrored?.current_node).toBe('n_cave_fork')
      expect(mirrored?.state_revision).toBeGreaterThanOrEqual(5)
    })
  })

  it('saving a bookmark issues a new PUT instead of being deduped as a no-op', async () => {
    // I5: persist()'s dedup signature includes save_slots specifically so a
    // bookmark-only change (no move, no var_state change) is not mistaken
    // for a repeat of the last save and silently dropped.
    const bodies: ReadingState[] = []
    const api: SyncApi = {
      putReadingState: (_p, _s, body) => {
        bodies.push(body)
        return Promise.resolve<PutResponse>({
          status: 200,
          row: { ...body, state_revision: bodies.length },
        })
      },
    }
    render(
      <MemoryRouter>
        <ReaderPage
          api={api}
          fetchStory={() => Promise.resolve(lantern)}
          profileId="p_bookmark_dedup"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0].save_slots).toEqual({})

    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    fireEvent.click(screen.getByTestId('save-bookmark'))

    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(Object.keys(bodies[1].save_slots)).toHaveLength(1)
    // Only the bookmark changed; position must be untouched by saving it.
    expect(bodies[1].current_node).toBe(bodies[0].current_node)
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

  it('posts a completion when the story reaches an ending', async () => {
    const recordCompletion = vi.fn(() => Promise.resolve({ is_new: true, found: 1, total: 4 }))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          recordCompletion={recordCompletion}
          profileId="p_complete"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
    fireEvent.click(await screen.findByTestId('choice-c_dark_passage'))
    await waitFor(() => expect(recordCompletion).toHaveBeenCalledTimes(1))
    expect(recordCompletion).toHaveBeenCalledWith({
      profile_id: 'p_complete',
      storybook_id: 's_lantern_cave',
      version: 1,
      ending_id: 'e_treasure_found',
    })
  })

  // A distinct profileId from the test above: that test's ended-state persist()
  // fires fire-and-forget (handleProgress does not await it) and can still be
  // in flight when the test returns; a shared profileId risks its IndexedDB
  // write landing after this test's beforeEach resets the db handle, resuming
  // this test straight into the ended state instead of the start passage.
  it('still shows the ending screen when the completion post fails', async () => {
    const recordCompletion = vi.fn(() => Promise.reject(new Error('boom')))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          recordCompletion={recordCompletion}
          profileId="p_complete_fail"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
    fireEvent.click(await screen.findByTestId('choice-c_dark_passage'))
    expect(await screen.findByTestId('ending-screen')).toBeTruthy()
  })

  // W0.3 (design review 2026-08-01 section 3.4): the completion POST's own
  // response drives the ending-screen tracker directly, with no second,
  // racing GET, and distinguishes a first find from a repeat.
  it('renders the NEW-ending tracker from the completion response, without a reading-history fetch', async () => {
    const recordCompletion = vi.fn(() => Promise.resolve({ is_new: true, found: 1, total: 4 }))
    const fetchReadingHistory = vi.fn(() => Promise.resolve([]))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          recordCompletion={recordCompletion}
          fetchReadingHistory={fetchReadingHistory}
          profileId="p_complete_new"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
    fireEvent.click(await screen.findByTestId('choice-c_dark_passage'))
    expect(
      await screen.findByText('You found a NEW ending! 1 of 4 found so far.')
    ).toBeInTheDocument()
    expect(fetchReadingHistory).not.toHaveBeenCalled()
  })

  it('falls back to the reading-history fetch when the completion POST rejects', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const recordCompletion = vi.fn(() => Promise.reject(new Error('boom')))
    const fetchReadingHistory = vi.fn(() =>
      Promise.resolve([
        {
          storybook_id: 's_lantern_cave',
          title: 'Lantern',
          endings_found: 1,
          ending_ids: ['e_treasure_found'],
          total_endings: 4,
          in_progress: false,
          last_activity_at: '2026-07-01T00:00:00Z',
        },
      ])
    )
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          recordCompletion={recordCompletion}
          fetchReadingHistory={fetchReadingHistory}
          profileId="p_complete_fallback"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
    fireEvent.click(await screen.findByTestId('choice-c_dark_passage'))
    expect(
      await screen.findByText('You found ending 1 of 4! Read again to find more.')
    ).toBeInTheDocument()
    expect(fetchReadingHistory).toHaveBeenCalledWith('p_complete_fallback')
    errorSpy.mockRestore()
  })

  const SERVER_RESUME: ReadingState = {
    current_node: 'n_cave_fork',
    var_state: { has_lantern: true },
    path: ['n_entrance', 'n_cave_fork'],
    visit_set: ['n_entrance', 'n_cave_fork'],
    version: 1,
    state_revision: 4,
    save_slots: {},
  }

  it('resumes from server state when the local cache is cold', async () => {
    const fetchServerState = vi.fn(() => Promise.resolve<ReadingState | null>(SERVER_RESUME))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          fetchServerState={fetchServerState}
          profileId="p_cold"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(fetchServerState).toHaveBeenCalledOnce()
    // Resumed at the cave fork with the lantern, so the gated choice is visible.
    expect(screen.getByTestId('passage-body').textContent).toContain('splits')
    expect(screen.getByTestId('choice-c_dark_passage')).toBeTruthy()
  })

  it('prefers the local cache over server state when both exist', async () => {
    const local: ReadingState = {
      current_node: 'n_cave_fork',
      var_state: { has_lantern: true },
      path: ['n_entrance', 'n_cave_fork'],
      visit_set: ['n_entrance', 'n_cave_fork'],
      version: 1,
      state_revision: 3,
      save_slots: {},
    }
    await putReadingState('p_both', 's_lantern_cave', local)
    const fetchServerState = vi.fn(() => Promise.resolve<ReadingState | null>(SERVER_RESUME))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          fetchServerState={fetchServerState}
          profileId="p_both"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(fetchServerState).not.toHaveBeenCalled()
  })

  it('starts fresh when cold cache and the server has no state (null)', async () => {
    const fetchServerState = vi.fn(() => Promise.resolve<ReadingState | null>(null))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          fetchServerState={fetchServerState}
          profileId="p_none"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    // Fresh start renders the start passage (the lantern intro).
    expect(screen.getByTestId('passage-body').textContent).toContain('lantern')
  })

  it('starts fresh (no offline screen) when the server fallback is offline', async () => {
    const fetchServerState = vi.fn(() => Promise.reject(new OfflineError()))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          fetchServerState={fetchServerState}
          profileId="p_off"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    // The story is already in hand, so a failed resume fetch must not block reading.
    await screen.findByTestId('reader')
  })

  it('does not reload in a loop when fetchServerState/recordCompletion are omitted', async () => {
    // Regression for an unbounded reload loop: default-parameter EXPRESSIONS
    // (`fetchServerState = () => ...`) mint a fresh function reference every
    // render, which used to change `load`'s useCallback identity every
    // render, re-firing the mount effect and forcing another render
    // (~650 GET calls observed in 500ms). Omitting both optional props here
    // exercises the module-level default constants (NO_SERVER_STATE,
    // NO_RECORD_COMPLETION); the read-state port must settle to a small,
    // bounded call count, not grow unbounded while this test waits.
    const getReadingStateSpy = vi.spyOn(db, 'getReadingState')
    const fetchStory = vi.fn(() => Promise.resolve(lantern))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={fetchStory}
          profileId="p_no_loop"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    // Let the app settle; a reload loop would keep firing calls during this
    // window instead of going quiet after the initial load.
    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(getReadingStateSpy.mock.calls.length).toBeLessThanOrEqual(2)
  })

  it('does not mirror a stale server payload over newer local state (overlapping generations)', async () => {
    // Regression: the mirror write (putReadingState after a server hit) used
    // to run unconditionally once fetchServerState resolved, gated only by a
    // stale() check on the LATER setPageState call. A superseded load
    // generation whose fetchServerState hangs can resolve after a newer
    // generation has already written fresher local state (persist() writes
    // IndexedDB before the network); the old server payload must not
    // clobber it.
    const oldServerState: ReadingState = {
      current_node: 'n_entrance',
      var_state: {},
      path: ['n_entrance'],
      visit_set: ['n_entrance'],
      version: 1,
      state_revision: 1,
      save_slots: {},
    }
    const newerLocalState: ReadingState = {
      current_node: 'n_cave_fork',
      var_state: { has_lantern: true },
      path: ['n_entrance', 'n_cave_fork'],
      visit_set: ['n_entrance', 'n_cave_fork'],
      version: 1,
      state_revision: 7,
      save_slots: {},
    }
    let resolveHangingFetch: ((value: ReadingState | null) => void) | undefined
    const fetchServerState = vi.fn(
      () =>
        new Promise<ReadingState | null>((resolve) => {
          resolveHangingFetch = resolve
        })
    )
    const { rerender } = render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          fetchServerState={fetchServerState}
          profileId="p_overlap"
          storybookId="s_lantern_cave"
          version={1}
        />
      </MemoryRouter>
    )
    // Wait for the first generation's fetchServerState call to be in flight.
    await waitFor(() => expect(fetchServerState).toHaveBeenCalledTimes(1))
    // A newer generation (e.g. a remount/retry) writes fresher local state,
    // simulating ongoing play that has since progressed past the cold-cache
    // moment the first generation observed.
    await putReadingState('p_overlap', 's_lantern_cave', newerLocalState)
    // Force a second load generation with a resolvable server fetch so the
    // page actually reaches 'reading' (mirroring a remount/retry after the
    // newer local write landed).
    const fetchServerStateSecond = vi.fn(() => Promise.resolve<ReadingState | null>(null))
    rerender(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(lantern)}
          fetchServerState={fetchServerStateSecond}
          profileId="p_overlap"
          storybookId="s_lantern_cave"
          version={1}
          deviceId="device-2"
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    // Now let the first (stale) generation's hanging fetch resolve with the
    // old server payload; it must not be mirrored over the newer local row.
    resolveHangingFetch?.(oldServerState)
    await waitFor(() => expect(fetchServerState).toHaveResolved())
    // Give a would-be (buggy) mirror write a chance to land before asserting.
    await new Promise((resolve) => setTimeout(resolve, 50))
    const rowAfter = await getReadingState('p_overlap', 's_lantern_cave')
    // Compare current_node/var_state, not state_revision: the reader's own
    // mount-time persist() legitimately re-stamps the revision from the save
    // API response, which is an unrelated concern from the mirror-write bug
    // under test here. What must never happen is the stale generation's old
    // server node/vars overwriting the newer local ones.
    expect(rowAfter?.current_node).not.toBe(oldServerState.current_node)
    expect(rowAfter?.current_node).toBe(newerLocalState.current_node)
  })

  // Task 3 fixture shape (see player/engine.test.ts "startContinuation"):
  // n_one is the start node, n_two has an on_enter effect that increments
  // courage by 1 on top of whatever is seeded.
  const continuationStory: Storybook = {
    schema_version: '2.0',
    id: 's_continuation_seed',
    version: 1,
    title: 'Continuation Seed',
    metadata: {},
    variables: [{ name: 'courage', type: 'int', initial: 0, min: 0, max: 5 }],
    start_node: 'n_one',
    nodes: [
      { id: 'n_one', body: 'chapter one starts', is_ending: false, choices: [] },
      {
        id: 'n_two',
        body: 'chapter two starts',
        is_ending: false,
        on_enter: [{ op: 'inc', var: 'courage', value: 1 }],
        choices: [],
      },
    ],
  }

  it('seeds a fresh read from a continuation', async () => {
    const fetchServerState = vi.fn(() => Promise.resolve<ReadingState | null>(null))
    const continuation: ContinuationSeed = { entryNode: 'n_two', varState: { courage: 2 } }
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(continuationStory)}
          fetchServerState={fetchServerState}
          continuation={continuation}
          profileId="p_seed"
          storybookId="s_continuation_seed"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(screen.getByTestId('passage-body').textContent).toContain('chapter two starts')
    // The seed persist is an async effect, so the reader painting chapter two
    // does not mean the IndexedDB write has landed: on a loaded runner the row
    // reads back `undefined` and the assertion fails (three unrelated PRs so
    // far, #545/#598/#609). Retry the read rather than the render. This still
    // fails if the product stops persisting at all, because waitFor exhausts
    // its timeout on a row that never appears.
    await waitFor(async () => {
      const row = await getReadingState('p_seed', 's_continuation_seed')
      expect(row?.current_node).toBe('n_two')
      // seeded 2, then n_two's on_enter inc applies on top
      expect(row?.var_state).toEqual({ courage: 3 })
    })
  })

  it('ignores a continuation when saved progress exists', async () => {
    const savedOnServer: ReadingState = {
      current_node: 'n_one',
      var_state: { courage: 5 },
      path: ['n_one'],
      visit_set: ['n_one'],
      version: 1,
      state_revision: 2,
      save_slots: {},
    }
    const fetchServerState = vi.fn(() => Promise.resolve<ReadingState | null>(savedOnServer))
    const continuation: ContinuationSeed = { entryNode: 'n_two', varState: { courage: 2 } }
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(continuationStory)}
          fetchServerState={fetchServerState}
          continuation={continuation}
          profileId="p_seed_saved"
          storybookId="s_continuation_seed"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    // Saved progress wins: resumes at n_one with the saved var_state, no
    // continuation jump to n_two and no seeding.
    expect(screen.getByTestId('passage-body').textContent).toContain('chapter one starts')
    // Same async-persist race as the seeding test above: this row is mirrored
    // from the server response, so it also starts nonexistent locally and can
    // read back `undefined` before the write lands.
    await waitFor(async () => {
      const row = await getReadingState('p_seed_saved', 's_continuation_seed')
      expect(row?.current_node).toBe('n_one')
      expect(row?.var_state).toEqual({ courage: 5 })
    })
  })

  it('ignores a continuation when local (IndexedDB) progress exists', async () => {
    // The server-origin variant above resumes via fetchServerState; this one
    // pins the other no-clobber leg: progress already in the local cache must
    // win over the seed, and the local row must survive unchanged.
    const localSaved: ReadingState = {
      current_node: 'n_one',
      var_state: { courage: 4 },
      path: ['n_one'],
      visit_set: ['n_one'],
      version: 1,
      state_revision: 3,
      save_slots: {},
    }
    await putReadingState('p_seed_local', 's_continuation_seed', localSaved)
    const fetchServerState = vi.fn(() => Promise.resolve<ReadingState | null>(null))
    const continuation: ContinuationSeed = { entryNode: 'n_two', varState: { courage: 2 } }
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(continuationStory)}
          fetchServerState={fetchServerState}
          continuation={continuation}
          profileId="p_seed_local"
          storybookId="s_continuation_seed"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    // Local progress wins: no continuation jump, no server consult, and the
    // stored row keeps the local position and vars.
    expect(screen.getByTestId('passage-body').textContent).toContain('chapter one starts')
    expect(fetchServerState).not.toHaveBeenCalled()
    const row = await getReadingState('p_seed_local', 's_continuation_seed')
    expect(row?.current_node).toBe('n_one')
    expect(row?.var_state).toEqual({ courage: 4 })
  })

  it('shows the error screen (not a stuck Loading) when the continuation seed cannot start', async () => {
    // A corrupt blob whose start_node points at no node: startContinuation
    // throws while seeding, and load() must map that to the error phase.
    const corrupt: Storybook = {
      ...continuationStory,
      id: 's_corrupt_seed',
      start_node: 'n_missing',
    }
    const continuation: ContinuationSeed = { entryNode: null }
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(corrupt)}
          fetchServerState={() => Promise.resolve(null)}
          continuation={continuation}
          profileId="p_seed_corrupt"
          storybookId="s_corrupt_seed"
          version={1}
        />
      </MemoryRouter>
    )
    expect(await screen.findByText('Something went wrong')).toBeTruthy()
    expect(screen.queryByTestId('loading')).toBeNull()
  })

  it('forwards the continuation seed to Reader so Read again restarts at the entry node, not the book start (issue #460)', async () => {
    // Extends continuationStory's shape with a real choice path to an ending.
    // load() seeds initialReading at n_two regardless of whether ReaderPage
    // forwards `continuation` to Reader, so that alone cannot catch a dropped
    // wiring line; RESTART is the discriminating moment, since it is Reader's
    // OWN `continuation` prop (not ReaderPage's initialReading) that decides
    // where a restart lands.
    const continuationSeriesStory: Storybook = {
      ...continuationStory,
      id: 's_continuation_restart',
      nodes: [
        {
          id: 'n_one',
          body: 'chapter one starts',
          is_ending: false,
          choices: [{ id: 'c_go', label: 'Go', target: 'n_two' }],
        },
        {
          id: 'n_two',
          body: 'chapter two starts',
          is_ending: false,
          on_enter: [{ op: 'inc', var: 'courage', value: 1 }],
          choices: [{ id: 'c_end', label: 'Finish', target: 'n_end' }],
        },
        { id: 'n_end', body: 'the end', is_ending: true, choices: [] },
      ],
    }
    const continuation: ContinuationSeed = { entryNode: 'n_two', varState: { courage: 2 } }
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(continuationSeriesStory)}
          fetchServerState={() => Promise.resolve(null)}
          continuation={continuation}
          profileId="p_seed_restart"
          storybookId="s_continuation_restart"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(screen.getByTestId('passage-body').textContent).toContain('chapter two starts')

    fireEvent.click(screen.getByTestId('choice-c_end'))
    expect(await screen.findByTestId('ending-screen')).toBeTruthy()

    fireEvent.click(screen.getByTestId('restart'))

    // A restart that dropped the continuation seed here would fall back to
    // start(): n_one and "chapter one starts", never n_two again.
    await waitFor(() => {
      expect(screen.getByTestId('passage-body').textContent).toContain('chapter two starts')
    })
    expect(screen.getByTestId('passage-body').textContent).not.toContain('chapter one starts')
  })
})

describe('ReaderPage personalization (ADR-023 C3d)', () => {
  it('passes a resolved values payload down to the Reader', async () => {
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(sentinelStory)}
          profileId="p_pers_on"
          storybookId="s_sentinel"
          version={1}
          fetchPersonalizationValues={() => Promise.resolve(valuesPayload())}
        />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByTestId('passage-body')).toHaveTextContent('Then Maya ran')
    })
  })

  it('passes null when no fetcher is provided (flag off)', async () => {
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(sentinelStory)}
          profileId="p_pers_off"
          storybookId="s_sentinel"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(screen.getByTestId('passage-body')).toHaveTextContent('Then Explorer ran')
  })

  it('still renders the story when the values fetch rejects', async () => {
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(sentinelStory)}
          profileId="p_pers_fail"
          storybookId="s_sentinel"
          version={1}
          fetchPersonalizationValues={() => Promise.reject(new Error('boom'))}
        />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByTestId('reader')).toBeInTheDocument()
    })
  })
})

describe('deriveCharacterSeed (ADR-028 Task 9)', () => {
  it('returns no character and no seed for a not-yet-loaded reading state', () => {
    expect(deriveCharacterSeed(undefined)).toEqual({ characterName: null, seed: undefined })
  })

  it('reads the bound character name and seed off a view-shaped reading state', () => {
    const state = withCharacterSeed(
      {
        current_node: 'n_gate',
        var_state: { has_sword: false },
        path: ['n_gate'],
        visit_set: ['n_gate'],
        version: 1,
        state_revision: 0,
        save_slots: {},
      },
      'Astra',
      { has_sword: true }
    )
    expect(deriveCharacterSeed(state)).toEqual({
      characterName: 'Astra',
      seed: { has_sword: true },
    })
  })

  // Named for what this test actually observes: it calls deriveCharacterSeed
  // directly and inspects its return value, so it pins the conversion AT THE
  // BOUNDARY. It renders nothing, so it cannot speak for what the rendered
  // reader receives; "carries the character seed through RESTART inside the
  // reader" below is the test that observes the rendered consequence.
  it('converts a null seed_var_state to undefined at the boundary', () => {
    // The real 422-shaped trap this guards: the server sends `null` (JSON),
    // not an absent key, when no character is bound. `readerMachine`'s
    // ReaderInput.seed is typed `VarState | undefined`, and safeStart
    // branches on `seed === undefined` -- `null !== undefined`, so piping the
    // raw value through would silently swap which of start()/
    // startContinuation() the machine calls on every RESTART and Go back.
    const state = withCharacterSeed(
      {
        current_node: 'n_gate',
        var_state: {},
        path: ['n_gate'],
        visit_set: ['n_gate'],
        version: 1,
        state_revision: 0,
        save_slots: {},
      },
      null,
      null
    )
    const result = deriveCharacterSeed(state)
    expect(result.seed).toBeUndefined()
    // toBeUndefined() alone would also pass a broken `?? null` conversion
    // read loosely, since `null` is falsy too; Object.is pins the exact
    // value, not just its truthiness.
    expect(Object.is(result.seed, null)).toBe(false)
  })
})

describe('ReaderPage character binding in the reader chrome (ADR-028 Task 9, closes #460)', () => {
  it("shows the bound character's name in the reader chrome", async () => {
    const saved = withCharacterSeed(
      {
        current_node: 'n_gate',
        var_state: { has_sword: false },
        path: ['n_gate'],
        visit_set: ['n_gate'],
        version: 1,
        state_revision: 0,
        save_slots: {},
      },
      'Astra',
      { has_sword: false }
    )
    await putReadingState('p_char_on', 's_seed', saved)
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(seedStory)}
          profileId="p_char_on"
          storybookId="s_seed"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(screen.getByTestId('reader-character-name')).toHaveTextContent('Astra')
  })

  it('shows no character chrome and no placeholder when no character is bound', async () => {
    const saved = withCharacterSeed(
      {
        current_node: 'n_gate',
        var_state: { has_sword: false },
        path: ['n_gate'],
        visit_set: ['n_gate'],
        version: 1,
        state_revision: 0,
        save_slots: {},
      },
      null,
      null
    )
    await putReadingState('p_char_off', 's_seed', saved)
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(seedStory)}
          profileId="p_char_off"
          storybookId="s_seed"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(screen.queryByTestId('reader-character-name')).toBeNull()
  })

  it('carries the character seed through RESTART inside the reader', async () => {
    // Land directly on the ending so "Read again" is available without
    // walking the story; the seed's effect is only observable at n_gate,
    // which RESTART returns to.
    const savedAtEnding = withCharacterSeed(
      {
        current_node: 'n_gate_end',
        var_state: { has_sword: false },
        path: ['n_gate', 'n_gate_end'],
        visit_set: ['n_gate', 'n_gate_end'],
        version: 1,
        state_revision: 0,
        save_slots: {},
      },
      'Astra',
      { has_sword: true }
    )
    await putReadingState('p_char_restart', 's_seed', savedAtEnding)
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(seedStory)}
          profileId="p_char_restart"
          storybookId="s_seed"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('ending-screen')
    fireEvent.click(screen.getByTestId('restart'))
    await screen.findByTestId('reader')
    // Only reachable if RESTART re-derived the start via the carried seed
    // (startContinuation(story, null, { has_sword: true })) rather than the
    // story's declared initial (has_sword: false, which would hide this
    // choice).
    expect(screen.getByTestId('choice-c_sword')).toBeTruthy()
  })
})

describe('ReaderPage fresh-read character seeding (ADR-028 Task 9, I1)', () => {
  it("seeds a fresh read from the profile's active character", async () => {
    // No local row and no server row: the genuinely fresh case, where nothing
    // has snapshotted a seed yet and the pre-fix code opened from the story's
    // declared initials (has_sword: false), which is issue #460's headline
    // defect.
    const fetchActiveCharacter = vi.fn(() =>
      Promise.resolve<CharacterBinding | null>({
        characterName: 'Astra',
        seed: { has_sword: true },
      })
    )
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(seedStory)}
          fetchServerState={() => Promise.resolve<ReadingState | null>(null)}
          fetchActiveCharacter={fetchActiveCharacter}
          profileId="p_fresh_char"
          storybookId="s_seed"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    expect(fetchActiveCharacter).toHaveBeenCalledWith('p_fresh_char')
    // The discriminator: c_sword's condition is `{ var: 'has_sword' }`, which
    // is false under the story's declared initial. It can only be visible if
    // the fetched seed genuinely reached the machine's start.
    expect(screen.getByTestId('choice-c_sword')).toBeTruthy()
    expect(screen.getByTestId('reader-character-name')).toHaveTextContent('Astra')
  })

  it('opens unseeded when the profile has no active character', async () => {
    const fetchActiveCharacter = vi.fn(() => Promise.resolve<CharacterBinding | null>(null))
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(seedStory)}
          fetchServerState={() => Promise.resolve<ReadingState | null>(null)}
          fetchActiveCharacter={fetchActiveCharacter}
          profileId="p_fresh_nochar"
          storybookId="s_seed"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    // Pre-ADR-028 behavior exactly: declared initials, no chrome, no error.
    expect(screen.queryByTestId('choice-c_sword')).toBeNull()
    expect(screen.getByTestId('choice-c_plain')).toBeTruthy()
    expect(screen.queryByTestId('reader-character-name')).toBeNull()
  })

  it('does not seed a continuation read from the active character', async () => {
    // A WS-G series continuation already built its own opening state from the
    // previous book's carried variables. Layering the character seed on top
    // would invent a client-side merge the server has no counterpart for, and
    // would make RESTART drop the series carry.
    const fetchActiveCharacter = vi.fn(() =>
      Promise.resolve<CharacterBinding | null>({
        characterName: 'Astra',
        seed: { has_sword: true },
      })
    )
    const continuation: ContinuationSeed = { entryNode: null, varState: { has_sword: false } }
    render(
      <MemoryRouter>
        <ReaderPage
          api={okApi()}
          fetchStory={() => Promise.resolve(seedStory)}
          fetchServerState={() => Promise.resolve<ReadingState | null>(null)}
          fetchActiveCharacter={fetchActiveCharacter}
          continuation={continuation}
          profileId="p_cont_char"
          storybookId="s_seed"
          version={1}
        />
      </MemoryRouter>
    )
    await screen.findByTestId('reader')
    // The continuation carry wins outright: the character lookup is never even
    // made, so there is no seed to merge and no name to show.
    expect(fetchActiveCharacter).not.toHaveBeenCalled()
    expect(screen.queryByTestId('choice-c_sword')).toBeNull()
    expect(screen.queryByTestId('reader-character-name')).toBeNull()
  })
})

/**
 * ADR-026 flowed-stop mount (UW-F40).
 *
 * At bands 8-11 and up the reader walks the whole opening stop before the
 * child touches anything, so Reader's progress effect reports MORE THAN ONE
 * reading state inside a single save round-trip. `persist()` stamps
 * `state_revision` from `revisionRef.current` synchronously, and that ref is
 * only advanced by a save's RESPONSE, so the second emission carries a
 * revision the first has already consumed and the real server rejects it.
 * The 409 branch then remounts the Reader, which replays the same two
 * emissions, so the conflict is self-sustaining rather than transient.
 *
 * These tests use a server double that enforces the same optimistic
 * concurrency precondition the real `PUT /v1/reading-state` enforces. The
 * suite's shared `okApi()` returns 200 for EVERY put whatever revision it
 * carries, which is exactly why a revision-stamping defect stayed invisible
 * to every other test in this file.
 */
describe('ReaderPage flowed-stop mount does not conflict with itself (UW-F40)', () => {
  // PL-25 shape: the first decision lands at least two nodes in, so the
  // opening node has exactly one choice and flows into the decision node.
  // This is the same shape as the seeded s_tide_pools (n_open -> n_start).
  const flowedStory: Storybook = {
    schema_version: '2.0',
    id: 's_flowed',
    version: 1,
    title: 'Flowed Opening',
    metadata: {},
    variables: [],
    start_node: 'n_open',
    nodes: [
      {
        id: 'n_open',
        body: 'The trail begins.',
        is_ending: false,
        choices: [{ id: 'c_on', label: 'Walk on', target: 'n_start' }],
      },
      {
        id: 'n_start',
        body: 'Two paths wait.',
        is_ending: false,
        choices: [
          { id: 'c_left', label: 'Left', target: 'n_end' },
          { id: 'c_right', label: 'Right', target: 'n_end' },
        ],
      },
      {
        id: 'n_end',
        body: 'The end.',
        is_ending: true,
        choices: [],
        ending: { id: 'e_done', kind: 'completion', valence: 'neutral', title: 'Done' },
      },
    ],
  }

  interface RecordedPut {
    current_node: string
    sent_revision: number
    status: number
  }

  /**
   * A server double that rejects any put whose `state_revision` is not the
   * one it currently holds, mirroring the real endpoint. `cap` exists only so
   * a runaway save/conflict cycle terminates: past it every put is accepted,
   * which turns a hang into a readable assertion failure.
   */
  function concurrencyCheckedApi(recorded: RecordedPut[], cap = 12): SyncApi {
    let serverRow: ReadingState | null = null
    let serverRevision = 0
    const accept = (body: ReadingState): PutResponse => {
      serverRevision += 1
      serverRow = { ...body, state_revision: serverRevision }
      return { status: 200, row: serverRow }
    }
    return {
      putReadingState: (_p, _s, body) => {
        if (recorded.length >= cap) {
          return Promise.resolve<PutResponse>(accept(body))
        }
        if (body.state_revision !== serverRevision) {
          recorded.push({
            current_node: body.current_node,
            sent_revision: body.state_revision,
            status: 409,
          })
          return Promise.resolve<PutResponse>({
            status: 409,
            currentRow: serverRow ?? { ...body, state_revision: serverRevision },
          })
        }
        recorded.push({
          current_node: body.current_node,
          sent_revision: body.state_revision,
          status: 200,
        })
        return Promise.resolve<PutResponse>(accept(body))
      },
    }
  }

  /**
   * Polls until the count stops moving, rather than sleeping a fixed span:
   * the claim under test is that saving STOPS, so the test has to observe
   * quiescence rather than assume a duration is long enough for it.
   */
  async function settle(read: () => number): Promise<number> {
    let last = -1
    let stableTicks = 0
    while (stableTicks < 3) {
      await new Promise((resolve) => setTimeout(resolve, 10))
      const now = read()
      if (now === last) {
        stableTicks += 1
      } else {
        stableTicks = 0
        last = now
      }
    }
    return last
  }

  it('sends no self-conflicting save while flowing the opening stop', async () => {
    const puts: RecordedPut[] = []
    render(
      <MemoryRouter>
        <ReaderPage
          api={concurrencyCheckedApi(puts)}
          fetchStory={() => Promise.resolve(flowedStory)}
          profileId="p_flow"
          storybookId="s_flowed"
          version={1}
          ageBand="8-11"
        />
      </MemoryRouter>
    )
    // The opening stop renders n_open and n_start as one screen.
    await waitFor(() =>
      expect(screen.getByTestId('passage-body').textContent).toContain('Two paths wait.')
    )
    const total = await settle(() => puts.length)

    // No other device has written this row, so a conflict here can only be
    // this reader colliding with its own in-flight save.
    expect(puts.filter((put) => put.status === 409)).toEqual([])
    // One save per emitted state (n_open, then n_start), and no more: a
    // higher count means the save/conflict cycle re-entered.
    expect(total).toBeLessThanOrEqual(2)
  })
})
