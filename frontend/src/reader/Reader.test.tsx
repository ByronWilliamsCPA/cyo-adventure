import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { StrictMode, type ReactNode } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { choose, startContinuation } from '../player/engine'
import type { ValuesPayload } from '../player/personalization'
import type { ContinuationSeed } from '../player/series'
import type { ReadingState, Storybook } from '../player/types'
import { clearChildSession, setChildSession } from '../auth/childSession'
import type { SubmitFlagParams } from '../api/readerApi'
import type { KidFlagCreatedView, ReadingHistoryItem } from '../client/types.gen'
import { ToastProvider } from '../notifications/ToastProvider'
import { Reader } from './Reader'

// choose() wraps the real implementation by default (every existing test
// below exercises genuine transitions); only the corrupted-transition test
// overrides it once to simulate a structurally invalid choice (a dangling
// target in corrupted cached data), which the real engine would reject with
// a throw. See "Reader corrupted-transition recovery" below.
vi.mock('../player/engine', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../player/engine')>()
  return { ...actual, choose: vi.fn(actual.choose) }
})

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')
const lantern = (
  JSON.parse(readFileSync(tracesPath, 'utf-8')) as {
    traces: { story: Storybook }[]
  }
).traces[0].story

// The same stop-composition conformance corpus stops.test.ts runs against
// player/stops.ts directly: reusing it here (rather than hand-rolling
// fixtures) means the Reader's ADR-026 integration is exercised against
// stories independently proven correct at the engine layer.
const stopTracesPath = path.resolve(here, '../../../schema/conformance/stop_traces.json')
const stopCases = (
  JSON.parse(readFileSync(stopTracesPath, 'utf-8')) as {
    cases: { name: string; story: Storybook }[]
  }
).cases
function stopStory(name: string): Storybook {
  const found = stopCases.find((c) => c.name === name)
  if (!found) throw new Error(`fixture missing: ${name}`)
  return found.story
}
// n_start (1 choice) -> n_hall (1 choice) -> n_gallery (2 choices, branch).
const flowToBranchStory = stopStory('flow_effects_in_order_to_branch')
// n_gate (2 choices) -> n_vestibule (1 choice, condition-gated) -> n_treasure_room (ending).
const flowToEndingStory = stopStory('condition_true_flows_through')
// n_p (1 choice) <-> n_q (1 choice): a single-choice cycle inside one stop.
const loopStory = stopStory('loop_back_ends_stop')
// n_home (1 choice) -> n_yard (branch) is stop 1; choosing c_shed leads into
// n_tool (1 choice) -> n_bench (branch), stop 2 -- two consecutive
// MULTI-node flowed stops, for exercising a stop-to-stop go back.
const backByStopStory = stopStory('back_by_stop_boundary')

// A minimal fixture (same shape as endedStory/endedSeriesStory below) whose
// body and ending title carry an ADR-023 sentinel, for the personalization
// resolution tests (C3e). "Continue" (choice id "c") is the only path, so a
// test can reach the ending without caring about lantern-specific branching.
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
      // The label carries a sentinel deliberately: labels never legally do
      // (generation/binding.py), but the Reader applies a defensive strip and
      // the tests below assert it.
      choices: [{ id: 'c', label: 'Follow {~HERO:Explorer~}', target: 'n_end' }],
    },
    {
      id: 'n_end',
      body: 'Then {~HERO:Explorer~} ran.',
      is_ending: true,
      choices: [],
      ending: {
        id: 'e_end',
        kind: 'success',
        valence: 'positive',
        title: "{~HERO:Explorer~}'s last stand",
      },
    },
  ],
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

// Mirrors ReaderPage.test.tsx's own StrictMode wrapper: the app always mounts
// under <StrictMode> (main.tsx), and mount-time effects double-invoke under
// it in dev, exercising exactly the hazard useFlowedStop.ts's dedup guard
// exists for.
function StrictModeWrapper({ children }: { children: ReactNode }) {
  return (
    <StrictMode>
      <MemoryRouter>{children}</MemoryRouter>
    </StrictMode>
  )
}

// A resumed-read reading state sitting on `nodeId`, with more than one entry
// in `path` (ADR-023 C5b: `atOpening` gates on path length, not just node id,
// so this is what distinguishes "the start node after going back" from "the
// start node on a fresh read").
function readingAt(nodeId: string): ReadingState {
  return {
    current_node: nodeId,
    var_state: {},
    path: ['n_start', nodeId],
    visit_set: ['n_start', nodeId],
    version: sentinelStory.version,
    state_revision: 0,
    save_slots: {},
  }
}

// jsdom's window.scrollTo exists but only logs "Not implemented"; the reader
// scrolls on every passage change, so stub it once per test to keep output
// quiet and make the scroll behavior assertable.
const scrollToMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal('scrollTo', scrollToMock)
})

afterEach(() => {
  cleanup()
  scrollToMock.mockClear()
  vi.unstubAllGlobals()
})

describe('Reader', () => {
  it('renders the start passage and its visible choices', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    expect(screen.getByTestId('passage-body').textContent).toContain('lantern')
    expect(screen.getByTestId('choice-c_take_lantern')).toBeTruthy()
    expect(screen.getByTestId('choice-c_ignore_lantern')).toBeTruthy()
    expect(screen.getByTestId('choice-c_take_lantern').textContent).toContain('›')
  })

  it('hides a choice whose condition is false', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_ignore_lantern'))
    // Without the lantern, the dark passage choice is not rendered.
    expect(screen.queryByTestId('choice-c_dark_passage')).toBeNull()
    expect(screen.getByTestId('choice-c_bright_tunnel')).toBeTruthy()
  })

  it('reveals the conditional choice once the lantern is taken', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    expect(screen.getByTestId('choice-c_dark_passage')).toBeTruthy()
  })

  it('shows the ending screen on reaching an ending', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
    expect(screen.getByTestId('ending-screen')).toBeTruthy()
    expect(screen.getByTestId('ending-id').textContent).toBe('e_treasure_found')
  })

  it('reports progress to onProgress', () => {
    const seen: string[] = []
    render(
      <MemoryRouter>
        <Reader story={lantern} onProgress={(r) => seen.push(r.current_node)} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    expect(seen).toContain('n_cave_fork')
  })

  it('reports the reached ending to onComplete exactly once', () => {
    const completed: string[] = []
    render(
      <MemoryRouter>
        <Reader story={lantern} onComplete={(id) => completed.push(id)} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
    expect(completed).toEqual(['e_treasure_found'])
  })

  it('does not re-post the same ending after Read again', () => {
    const completed: string[] = []
    render(
      <MemoryRouter>
        <Reader story={lantern} onComplete={(id) => completed.push(id)} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
    fireEvent.click(screen.getByTestId('restart'))
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
    expect(completed).toEqual(['e_treasure_found'])
  })

  it('does not re-post an earlier ending after a different one is reached (interleaved)', () => {
    // A -> B -> A must report [A, B], not [A, B, A]. A single-slot "last ending"
    // ref would forget A once B is reached and re-fire it; the completed-endings
    // set reports each distinct ending at most once per session.
    const completed: string[] = []
    render(
      <MemoryRouter>
        <Reader story={lantern} onComplete={(id) => completed.push(id)} profileId="p1" />
      </MemoryRouter>
    )
    // A: e_treasure_found (dark passage, gated on the lantern).
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
    fireEvent.click(screen.getByTestId('restart'))
    // B: e_safe_exit (bright tunnel).
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_bright_tunnel'))
    fireEvent.click(screen.getByTestId('restart'))
    // A again: already reported, so it must not fire a second time.
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
    expect(completed).toEqual(['e_treasure_found', 'e_safe_exit'])
  })
})

describe('Reader personalization (ADR-023 C3e)', () => {
  it('renders the personalized name in the passage when a payload is present', () => {
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" personalization={valuesPayload()} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('passage-body')).toHaveTextContent('Then Maya ran')
    expect(screen.getByTestId('passage-body')).not.toHaveTextContent('{~HERO')
  })

  it('renders the generic word when there is no payload', () => {
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" />
      </MemoryRouter>
    )
    expect(screen.getByTestId('passage-body')).toHaveTextContent('Then Explorer ran')
    expect(screen.getByTestId('passage-body')).not.toHaveTextContent('{~HERO')
  })

  it('strips markers to generic words even with the flag off', () => {
    // Deliberate strengthening of the Stage C spec (see Task C3f). The flag gates
    // the FETCH; the strip is unconditional, because ADR-023 section 10 forbids a
    // marker on any kid-facing surface regardless of opt-in state.
    expect(import.meta.env.VITE_FEATURE_PERSONALIZATION).toBeUndefined()
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" />
      </MemoryRouter>
    )
    const passage = screen.getByTestId('passage-body')
    expect(passage).toHaveTextContent('Then Explorer ran')
    expect(passage.textContent).not.toContain('{~')
    expect(passage.textContent).not.toContain('~}')
  })

  it('resolves the ending title', () => {
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" personalization={valuesPayload()} />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c'))
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent("Maya's last stand")
  })

  it('strips the ending title to its generic word on the generic path', () => {
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c'))
    const heading = screen.getByRole('heading', { level: 2 })
    expect(heading).toHaveTextContent("Explorer's last stand")
    expect(heading.textContent).not.toContain('{~')
  })

  it('defensively strips a sentinel in a choice label to its generic word, never the marker', () => {
    // Labels are stripped, not resolved: a personal value in a label would be
    // a new egress surface, so even with a payload present the label shows the
    // generic word.
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" personalization={valuesPayload()} />
      </MemoryRouter>
    )
    const label = screen.getByTestId('choice-c').textContent ?? ''
    expect(label).toContain('Follow Explorer')
    expect(label).not.toContain('{~')
    expect(label).not.toContain('Maya')
  })
})

describe('Reader dedication overlay (ADR-023 C5b)', () => {
  it('shows the dedication on the opening passage', () => {
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" personalization={valuesPayload()} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('dedication')).toBeInTheDocument()
  })

  it('hides the dedication once the child has moved on', () => {
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" personalization={valuesPayload()} />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c'))
    expect(screen.queryByTestId('dedication')).not.toBeInTheDocument()
  })

  it('shows no dedication on a resumed read that is past the start node', () => {
    render(
      <MemoryRouter>
        <Reader
          story={sentinelStory}
          profileId="p1"
          personalization={valuesPayload()}
          initialReading={readingAt('n_end')}
        />
      </MemoryRouter>
    )
    expect(screen.queryByTestId('dedication')).not.toBeInTheDocument()
  })

  it('shows no dedication without a payload', () => {
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" />
      </MemoryRouter>
    )
    expect(screen.queryByTestId('dedication')).not.toBeInTheDocument()
  })

  it('re-shows the dedication after going back to the opening page (by design)', () => {
    // The engine's back() truncates the recorded path, so a post-back return
    // to the start node is indistinguishable from a short read and
    // legitimately re-shows the dedication.
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" personalization={valuesPayload()} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('dedication')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('choice-c'))
    expect(screen.queryByTestId('dedication')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('go-back'))
    expect(screen.getByTestId('dedication')).toBeInTheDocument()
  })

  it('re-shows the dedication after Read again (RESTART)', () => {
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" personalization={valuesPayload()} />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c'))
    expect(screen.queryByTestId('dedication')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('restart'))
    expect(screen.getByTestId('dedication')).toBeInTheDocument()
  })
})

describe('Reader series continuation', () => {
  const seriesBlock = {
    series_id: 'ser-1',
    book_index: 1,
    series_entry_node: 'n_entrance',
    is_final: false,
    carries_state: true,
  }
  const seriesStory = { ...lantern, metadata: { ...lantern.metadata, series: seriesBlock } }
  const finalStory = {
    ...lantern,
    metadata: { ...lantern.metadata, series: { ...seriesBlock, is_final: true } },
  }
  const fetchNext = () =>
    Promise.resolve({
      storybook_id: 's_book2',
      version: 1,
      title: 'Book 2',
      series_entry_node: 'n_start',
      carries_state: true,
    })

  function reachEnding(story: Storybook, fetchSeriesNext?: typeof fetchNext) {
    render(
      <MemoryRouter>
        <Reader story={story} profileId="p1" fetchSeriesNext={fetchSeriesNext} />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
  }

  it('offers Continue the series for a satisfying ending of a non-final series book', async () => {
    reachEnding(seriesStory, fetchNext)
    expect(await screen.findByTestId('continue-series')).toBeTruthy()
  })

  it('does not offer continuation for the final book of a series', () => {
    reachEnding(finalStory, fetchNext)
    expect(screen.queryByTestId('continue-series')).toBeNull()
  })

  it('does not offer continuation for a non-series story', () => {
    reachEnding(lantern, fetchNext)
    expect(screen.queryByTestId('continue-series')).toBeNull()
  })

  it('does not offer continuation without a fetchSeriesNext prop', () => {
    reachEnding(seriesStory)
    expect(screen.queryByTestId('continue-series')).toBeNull()
  })

  // The lantern fixture only has satisfying endings, so the non-satisfying
  // boundary needs its own minimal story. The gate is on ending.kind
  // (SATISFYING_ENDING_KINDS = success/completion), not valence.
  function endedSeriesStory(ending: NonNullable<Storybook['nodes'][number]['ending']>): Storybook {
    return {
      schema_version: '2.0',
      id: 's_series_end',
      version: 1,
      title: 'Series End',
      metadata: { series: seriesBlock },
      variables: [],
      start_node: 'n_start',
      nodes: [
        {
          id: 'n_start',
          body: 'begin',
          is_ending: false,
          choices: [{ id: 'c_end', label: 'End it', target: 'n_end' }],
        },
        { id: 'n_end', body: 'done', is_ending: true, choices: [], ending },
      ],
    }
  }

  function reachAdHocEnding(story: Storybook) {
    render(
      <MemoryRouter>
        <Reader story={story} profileId="p1" fetchSeriesNext={fetchNext} />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_end'))
  }

  it('does not offer continuation for a non-satisfying ending (kind death)', () => {
    reachAdHocEnding(
      endedSeriesStory({ id: 'e_dead', kind: 'death', valence: 'negative', title: 'Lost' })
    )
    expect(screen.getByTestId('ending-screen')).toBeTruthy()
    expect(screen.queryByTestId('continue-series')).toBeNull()
  })

  it('gates on kind, not valence: a positive discovery ending offers no continuation', () => {
    reachAdHocEnding(
      endedSeriesStory({ id: 'e_found', kind: 'discovery', valence: 'positive', title: 'Found' })
    )
    expect(screen.getByTestId('ending-screen')).toBeTruthy()
    expect(screen.queryByTestId('continue-series')).toBeNull()
  })

  it('offers continuation at the satisfying boundary (kind completion)', async () => {
    reachAdHocEnding(
      endedSeriesStory({ id: 'e_done', kind: 'completion', valence: 'neutral', title: 'Done' })
    )
    expect(await screen.findByTestId('continue-series')).toBeTruthy()
  })
})

describe('Reader RESTART honors a continuation seed (issue #460)', () => {
  // Mirrors player/machine.test.ts's own "book2" fixture for this issue: book 2
  // of a series whose start node is a prologue a continuation read must skip,
  // and whose continuation entry node carries an on_enter effect that makes the
  // carried variables observably distinct from a fresh start's declared
  // initials. The two node bodies below are the discriminating signal: if
  // Reader ever stopped forwarding `continuation` into the machine's input,
  // RESTART would land back on the prologue instead of the entry node.
  const book2: Storybook = {
    schema_version: '2.0',
    id: 's_book2',
    version: 1,
    title: 'Book Two',
    metadata: {
      series: {
        series_id: 's_saga',
        book_index: 2,
        series_entry_node: 'n_woods',
        carries_state: true,
      },
    },
    variables: [
      { name: 'torch', type: 'bool', initial: false },
      { name: 'coins', type: 'int', initial: 0, min: 0, max: 9 },
    ],
    start_node: 'n_camp',
    nodes: [
      {
        id: 'n_camp',
        body: 'the prologue a continuation read is meant to skip',
        is_ending: false,
        choices: [{ id: 'c_torch', label: 'Take the torch.', target: 'n_woods' }],
      },
      {
        id: 'n_woods',
        body: 'woods',
        is_ending: false,
        on_enter: [{ op: 'inc', var: 'coins', value: 1 }],
        choices: [{ id: 'c_river', label: 'Cross the river.', target: 'n_river' }],
      },
      { id: 'n_river', body: 'river', is_ending: true, choices: [] },
    ],
  }
  const seed: ContinuationSeed = { entryNode: 'n_woods', varState: { torch: true, coins: 4 } }

  it('restarts to the continuation entry node with carried variables, not the book start node', () => {
    render(
      <MemoryRouter>
        <Reader
          story={book2}
          profileId="p1"
          continuation={seed}
          initialReading={startContinuation(book2, seed.entryNode, seed.varState)}
        />
      </MemoryRouter>
    )
    // The continuation read opens on the entry node, never the prologue.
    expect(screen.getByTestId('passage-body').textContent).toContain('woods')
    fireEvent.click(screen.getByTestId('choice-c_river'))
    expect(screen.getByTestId('ending-screen')).toBeTruthy()

    fireEvent.click(screen.getByTestId('restart'))

    // A restart that dropped the continuation seed would fall back to start():
    // current_node n_camp and the prologue body, never "woods".
    expect(screen.getByTestId('passage-body').textContent).toContain('woods')
    expect(screen.getByTestId('passage-body').textContent).not.toContain('prologue')
  })
})

describe('Reader passage change scroll and focus', () => {
  function renderLantern() {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
  }

  it('does not scroll or steal focus on the initial mount', () => {
    renderLantern()
    expect(scrollToMock).not.toHaveBeenCalled()
    expect(document.activeElement).not.toBe(screen.getByTestId('passage-body'))
  })

  it('scrolls smoothly to the top and focuses the new passage after a choice', () => {
    renderLantern()
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    expect(scrollToMock).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
    // Focus lands on the passage container so screen readers announce the new
    // passage from its start.
    expect(document.activeElement).toBe(screen.getByTestId('passage-body'))
  })

  it('scrolls without animation when the user prefers reduced motion', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(
        (query: string) =>
          ({ matches: query === '(prefers-reduced-motion: reduce)' }) as unknown as MediaQueryList
      )
    )
    renderLantern()
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    expect(scrollToMock).toHaveBeenCalledWith({ top: 0, behavior: 'auto' })
  })
})

describe('Reader ending progress and celebration', () => {
  function endedStory(ending: NonNullable<Storybook['nodes'][number]['ending']>): Storybook {
    return {
      schema_version: '2.0',
      id: 's_valence',
      version: 1,
      title: 'Valence',
      metadata: {},
      variables: [],
      start_node: 'n_start',
      nodes: [
        {
          id: 'n_start',
          body: 'begin',
          is_ending: false,
          choices: [{ id: 'c_end', label: 'End it', target: 'n_end' }],
        },
        { id: 'n_end', body: 'done', is_ending: true, choices: [], ending },
      ],
    }
  }

  function reachLanternEnding() {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
  }

  function reachEndingOf(story: Storybook) {
    render(
      <MemoryRouter>
        <Reader story={story} profileId="p1" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_end'))
  }

  it('shows a full, true progress bar with a finished label at an ending', () => {
    reachLanternEnding()
    const bar = screen.getByRole('progressbar')
    // A finished story never looks unfinished, and this is the one moment
    // the chrome shows a percent at all (W1.2/AL-029): the story is
    // genuinely done, so 100% is finally an honest claim.
    expect(bar.getAttribute('aria-valuenow')).toBe('100')
    expect(bar.getAttribute('aria-label')).toBe('You finished this story!')
  })

  it('shows the plain "Page N" position pill, not a percent bar, before the ending (W1.2/AL-029)', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    // No fabricated percent while reading: the corpus has no honest
    // "distance to the end" figure for the path a child actually took.
    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(screen.getByTestId('reader-position').textContent).toBe('Page 1')
  })

  it('celebrates a positive ending with the animated stars', () => {
    reachLanternEnding()
    const stars = screen.getByTestId('ending-celebration')
    // The celebrate-vs-calm distinction is purely decorative: the stars element
    // is aria-hidden (asserted below) and the ending's title/body prose are the
    // same either way, so there is no accessible/text signal to assert instead.
    // The --celebrate class token is the only observable difference, and its
    // visual effect (the CSS star burst) is not rendered in jsdom. Keep the
    // class assertion as the narrowest available proxy for that visual state.
    expect(stars.className).toContain('reader-ending__stars--celebrate')
    expect(stars.getAttribute('aria-hidden')).toBe('true')
  })

  it('celebrates a neutral ending too', () => {
    reachEndingOf(
      endedStory({ id: 'e_done', kind: 'completion', valence: 'neutral', title: 'Done' })
    )
    expect(screen.getByTestId('ending-celebration').className).toContain(
      'reader-ending__stars--celebrate'
    )
  })

  it('gives a negative ending the static warm treatment, not the celebration', () => {
    reachEndingOf(endedStory({ id: 'e_lost', kind: 'death', valence: 'negative', title: 'Lost' }))
    const stars = screen.getByTestId('ending-celebration')
    expect(stars.className).toBe('reader-ending__stars')
    expect(stars.className).not.toContain('--celebrate')
  })
})

type FetchReadingHistoryMock = (profileId: string) => Promise<ReadingHistoryItem[]>
type SubmitFlagMock = (params: SubmitFlagParams) => Promise<KidFlagCreatedView>

describe('Reader K6 endings tracker', () => {
  function reachLanternEnding(fetchReadingHistory?: FetchReadingHistoryMock) {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" fetchReadingHistory={fetchReadingHistory} />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByTestId('choice-c_dark_passage'))
  }

  it('shows the tracker after the celebration when total_endings > 1', async () => {
    const fetchReadingHistory = vi.fn<FetchReadingHistoryMock>().mockResolvedValue([
      {
        storybook_id: lantern.id,
        title: lantern.title,
        endings_found: 2,
        ending_ids: ['e_treasure_found', 'e_other'],
        total_endings: 4,
        in_progress: false,
        last_activity_at: '2026-07-01T00:00:00Z',
      },
    ])
    reachLanternEnding(fetchReadingHistory)
    expect(await screen.findByTestId('endings-tracker')).toHaveTextContent(
      'You found ending 2 of 4! Read again to find more.'
    )
    expect(fetchReadingHistory).toHaveBeenCalledWith('p1')
  })

  it('renders nothing when total_endings is 1 or fewer', async () => {
    const fetchReadingHistory = vi.fn<FetchReadingHistoryMock>().mockResolvedValue([
      {
        storybook_id: lantern.id,
        title: lantern.title,
        endings_found: 1,
        ending_ids: ['e_treasure_found'],
        total_endings: 1,
        in_progress: false,
        last_activity_at: '2026-07-01T00:00:00Z',
      },
    ])
    reachLanternEnding(fetchReadingHistory)
    await waitFor(() => expect(fetchReadingHistory).toHaveBeenCalled())
    expect(screen.queryByTestId('endings-tracker')).not.toBeInTheDocument()
  })

  it('renders nothing (no fetch attempted) when fetchReadingHistory is omitted', () => {
    reachLanternEnding()
    expect(screen.queryByTestId('endings-tracker')).not.toBeInTheDocument()
  })

  it('renders nothing on a lookup failure', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const fetchReadingHistory = vi
      .fn<FetchReadingHistoryMock>()
      .mockRejectedValue(new Error('boom'))
    reachLanternEnding(fetchReadingHistory)
    await waitFor(() => expect(fetchReadingHistory).toHaveBeenCalled())
    expect(screen.queryByTestId('endings-tracker')).not.toBeInTheDocument()
    errorSpy.mockRestore()
  })
})

describe('Reader K15 flag button', () => {
  afterEach(() => {
    clearChildSession()
  })

  it('does not render the flag button when submitFlag is omitted', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    expect(screen.queryByRole('button', { name: /tell a grown-up/i })).not.toBeInTheDocument()
  })

  it('does not render the flag button without a valid child session, even with submitFlag wired', () => {
    render(
      <MemoryRouter>
        <ToastProvider>
          <Reader story={lantern} profileId="p1" submitFlag={vi.fn<SubmitFlagMock>()} />
        </ToastProvider>
      </MemoryRouter>
    )
    expect(screen.queryByRole('button', { name: /tell a grown-up/i })).not.toBeInTheDocument()
  })

  it('renders the flag button in the chrome once a valid child session exists', () => {
    setChildSession({ token: 't', expiresAt: '2100-01-01T00:00:00Z', profileId: 'p1' })
    render(
      <MemoryRouter>
        <ToastProvider>
          <Reader story={lantern} profileId="p1" submitFlag={vi.fn<SubmitFlagMock>()} />
        </ToastProvider>
      </MemoryRouter>
    )
    expect(screen.getByRole('button', { name: /tell a grown-up/i })).toBeInTheDocument()
  })
})

describe('Reader corrupted-transition recovery', () => {
  it('recovers from a corrupted transition instead of crashing the reader', () => {
    // engine.choose() throws by contract on a structurally invalid choice (a
    // dangling target in corrupted cached data); this must never reach the
    // child as an uncaught exception mid-story.
    vi.mocked(choose).mockImplementationOnce(() => {
      throw new Error('dangling choice target')
    })
    const logSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      render(
        <MemoryRouter>
          <Reader story={lantern} profileId="p1" />
        </MemoryRouter>
      )
      fireEvent.click(screen.getByTestId('choice-c_take_lantern'))

      expect(screen.getByRole('alert')).toHaveTextContent(/stuck/i)
      expect(screen.queryByTestId('passage-body')).not.toBeInTheDocument()

      // "Start over" clears the error and resets to the start passage.
      fireEvent.click(screen.getByRole('button', { name: /start over/i }))
      expect(screen.getByTestId('passage-body').textContent).toContain('lantern')
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    } finally {
      logSpy.mockRestore()
    }
  })

  it('still offers a way back to the library from the corrupted-transition screen', () => {
    vi.mocked(choose).mockImplementationOnce(() => {
      throw new Error('dangling choice target')
    })
    const logSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      render(
        <MemoryRouter>
          <Reader story={lantern} profileId="p1" />
        </MemoryRouter>
      )
      fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
      expect(screen.getByRole('button', { name: /back to my books/i })).toBeInTheDocument()
    } finally {
      logSpy.mockRestore()
    }
  })
})

describe('Reader read-aloud (K7)', () => {
  // A minimal stand-in for SpeechSynthesisUtterance: real browsers fire
  // onend asynchronously once audio playback finishes; tests trigger it
  // directly instead of waiting on real speech.
  class MockUtterance {
    text: string
    onend: (() => void) | null = null
    onerror: (() => void) | null = null
    onboundary: ((event: { charIndex: number; name?: string }) => void) | null = null
    constructor(text: string) {
      this.text = text
    }
  }

  const speakMock = vi.fn()
  const cancelMock = vi.fn()

  // Defaults to a local default voice so the TTS egress guard (personalized
  // text only through voice.localService === true) permits personalized
  // speech; the non-local case overrides the voice list explicitly.
  function installSpeechSynthesis(
    voices: SpeechSynthesisVoice[] = [{ default: true, localService: true } as SpeechSynthesisVoice]
  ) {
    vi.stubGlobal('speechSynthesis', {
      speak: speakMock,
      cancel: cancelMock,
      getVoices: () => voices,
    })
    vi.stubGlobal('SpeechSynthesisUtterance', MockUtterance)
  }

  beforeEach(() => {
    speakMock.mockReset()
    cancelMock.mockReset()
  })

  function renderLantern(ttsEnabled: boolean) {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" ttsEnabled={ttsEnabled} />
      </MemoryRouter>
    )
  }

  it('does not render the toggle when tts_enabled is false, even with speechSynthesis present', () => {
    installSpeechSynthesis()
    renderLantern(false)
    expect(screen.queryByLabelText('Read this page aloud')).toBeNull()
  })

  it('does not render the toggle when speechSynthesis is absent, even when tts_enabled is true', () => {
    // Deliberately not installed.
    renderLantern(true)
    expect(screen.queryByLabelText('Read this page aloud')).toBeNull()
  })

  it('never auto-plays: speak is not called on mount even when available', () => {
    installSpeechSynthesis()
    renderLantern(true)
    expect(speakMock).not.toHaveBeenCalled()
  })

  it('speaks the passage body then the visible choice labels when tapped', () => {
    installSpeechSynthesis()
    renderLantern(true)
    const toggle = screen.getByLabelText('Read this page aloud')
    fireEvent.click(toggle)

    expect(screen.getByLabelText('Stop reading aloud')).toBeTruthy()
    expect(speakMock).toHaveBeenCalledTimes(1)
    const bodyUtterance = speakMock.mock.calls[0][0] as MockUtterance
    expect(bodyUtterance.text).toBe('A lantern lies near the entrance.')

    bodyUtterance.onend?.()
    expect(speakMock).toHaveBeenCalledTimes(2)
    const choicesUtterance = speakMock.mock.calls[1][0] as MockUtterance
    expect(choicesUtterance.text).toBe('Your choices are: Pick up the lantern., Walk inside.')
  })

  it('re-tapping while speaking stops speech', () => {
    installSpeechSynthesis()
    renderLantern(true)
    fireEvent.click(screen.getByLabelText('Read this page aloud'))
    expect(screen.getByLabelText('Stop reading aloud')).toBeTruthy()

    fireEvent.click(screen.getByLabelText('Stop reading aloud'))
    expect(cancelMock).toHaveBeenCalled()
    expect(screen.getByLabelText('Read this page aloud')).toBeTruthy()
  })

  it('cancels speech on a choice tap (navigation)', () => {
    installSpeechSynthesis()
    renderLantern(true)
    fireEvent.click(screen.getByLabelText('Read this page aloud'))
    expect(screen.getByLabelText('Stop reading aloud')).toBeTruthy()
    cancelMock.mockClear()

    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    expect(cancelMock).toHaveBeenCalled()
    expect(screen.getByLabelText('Read this page aloud')).toBeTruthy()
  })

  it('cancels speech on Go back', () => {
    installSpeechSynthesis()
    renderLantern(true)
    fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
    fireEvent.click(screen.getByLabelText('Read this page aloud'))
    expect(screen.getByLabelText('Stop reading aloud')).toBeTruthy()
    cancelMock.mockClear()

    fireEvent.click(screen.getByTestId('go-back'))
    expect(cancelMock).toHaveBeenCalled()
    expect(screen.getByLabelText('Read this page aloud')).toBeTruthy()
  })

  it('cancels speech on Leave', () => {
    installSpeechSynthesis()
    renderLantern(true)
    fireEvent.click(screen.getByLabelText('Read this page aloud'))
    cancelMock.mockClear()

    fireEvent.click(screen.getByRole('button', { name: 'Leave' }))
    expect(cancelMock).toHaveBeenCalled()
  })

  it('cancels speech on unmount', () => {
    installSpeechSynthesis()
    const { unmount } = render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" ttsEnabled />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByLabelText('Read this page aloud'))
    cancelMock.mockClear()

    unmount()
    expect(cancelMock).toHaveBeenCalled()
  })

  it('highlights the spoken word in the passage as onboundary events fire, and clears it once speech moves to the choices (P-5)', () => {
    installSpeechSynthesis()
    renderLantern(true)
    fireEvent.click(screen.getByLabelText('Read this page aloud'))
    const bodyUtterance = speakMock.mock.calls[0][0] as MockUtterance
    expect(bodyUtterance.text).toBe('A lantern lies near the entrance.')

    expect(document.querySelector('mark.cyo-passage__highlight')).toBeNull()

    act(() => {
      bodyUtterance.onboundary?.({ charIndex: 0, name: 'word' })
    })
    let mark = document.querySelector('mark.cyo-passage__highlight')
    expect(mark).toHaveTextContent('A')

    act(() => {
      bodyUtterance.onboundary?.({ charIndex: 2, name: 'word' })
    })
    mark = document.querySelector('mark.cyo-passage__highlight')
    expect(mark).toHaveTextContent('lantern')

    // Moving on to "Your choices are: ..." clears the highlight: there is
    // no rendered choice-list text in the passage to highlight against.
    act(() => {
      bodyUtterance.onend?.()
    })
    expect(document.querySelector('mark.cyo-passage__highlight')).toBeNull()
  })

  it('does not show the toggle on the corrupted-transition error screen', () => {
    installSpeechSynthesis()
    vi.mocked(choose).mockImplementationOnce(() => {
      throw new Error('dangling choice target')
    })
    const logSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      renderLantern(true)
      fireEvent.click(screen.getByTestId('choice-c_take_lantern'))
      expect(screen.getByRole('alert')).toHaveTextContent(/stuck/i)
      expect(screen.queryByLabelText('Read this page aloud')).toBeNull()
    } finally {
      logSpy.mockRestore()
    }
  })

  // ADR-023 C3e placement note: this lives here, not in useReadAloud.test.ts,
  // because the substitution under test (raw node.body vs. the resolved
  // bodyText) happens in Reader.tsx's speak() call site, not inside the hook
  // itself; useReadAloud.test.ts already covers the hook's own queueing
  // mechanics in isolation and has no notion of personalization.
  it('speaks the resolved passage, not the marker (local voice)', () => {
    installSpeechSynthesis()
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" personalization={valuesPayload()} ttsEnabled />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByLabelText('Read this page aloud'))
    expect(speakMock).toHaveBeenCalledTimes(1)
    const bodyUtterance = speakMock.mock.calls[0][0] as MockUtterance
    expect(bodyUtterance.text).toContain('Maya')
    expect(bodyUtterance.text).not.toContain('{~HERO')
  })

  it('speaks the generic passage through a non-local voice (TTS egress guard)', () => {
    // A non-local voice synthesizes server-side; the child's real name must
    // never ride that egress, so the generic-resolved text is spoken instead.
    installSpeechSynthesis([{ default: true, localService: false } as SpeechSynthesisVoice])
    render(
      <MemoryRouter>
        <Reader story={sentinelStory} profileId="p1" personalization={valuesPayload()} ttsEnabled />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByLabelText('Read this page aloud'))
    expect(speakMock).toHaveBeenCalledTimes(1)
    const bodyUtterance = speakMock.mock.calls[0][0] as MockUtterance
    expect(bodyUtterance.text).toContain('Explorer')
    expect(bodyUtterance.text).not.toContain('Maya')
    expect(bodyUtterance.text).not.toContain('{~HERO')
  })

  it('reads the whole flowed passage aloud, not just the first node (K7 + W1.1)', () => {
    installSpeechSynthesis()
    render(
      <MemoryRouter>
        <Reader story={flowToBranchStory} profileId="p1" ageBand="8-11" ttsEnabled />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByLabelText('Read this page aloud'))
    const bodyUtterance = speakMock.mock.calls[0][0] as MockUtterance
    expect(bodyUtterance.text).toContain('front door')
    expect(bodyUtterance.text).toContain('long hall')
    expect(bodyUtterance.text).toContain('two wings')
  })
})

describe('Reader stop-flow rendering (ADR-026, W1.1)', () => {
  it("keeps exactly today's one-node-per-page behavior when no band is known (default)", () => {
    render(
      <MemoryRouter>
        <Reader story={flowToBranchStory} profileId="p1" />
      </MemoryRouter>
    )
    // Only the FIRST node's body renders; n_hall/n_gallery prose is not on
    // the page yet, and the single choice reads as an ordinary "Continue".
    const body = screen.getByTestId('passage-body').textContent ?? ''
    expect(body).toContain('front door')
    expect(body).not.toContain('long hall')
    expect(body).not.toContain('two wings')
    expect(screen.getByTestId('choice-c_enter')).toBeTruthy()
  })

  it('flows consecutive single-choice nodes into one scrollable stop at 8-11', () => {
    render(
      <MemoryRouter>
        <Reader story={flowToBranchStory} profileId="p1" ageBand="8-11" />
      </MemoryRouter>
    )
    // One passage block carries all three node bodies as distinct
    // paragraphs (PassageText splits on blank lines): every node the stop
    // flowed through is visible, not just the first.
    const body = screen.getByTestId('passage-body').textContent ?? ''
    expect(body).toContain('front door')
    expect(body).toContain('long hall')
    expect(body).toContain('two wings')
    // The stop's own two choices render at the bottom; the single-choice
    // "Continue" from n_start/n_hall never appears as its own button.
    expect(screen.getByTestId('choice-c_left')).toBeTruthy()
    expect(screen.getByTestId('choice-c_right')).toBeTruthy()
    expect(screen.queryByTestId('choice-c_enter')).toBeNull()
    expect(screen.queryByTestId('choice-c_walk')).toBeNull()
  })

  it.each(['10-13', '13-16', '16+'])('also flows at band %s', (band) => {
    render(
      <MemoryRouter>
        <Reader story={flowToBranchStory} profileId="p1" ageBand={band} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('passage-body').textContent ?? '').toContain('two wings')
    expect(screen.getByTestId('choice-c_left')).toBeTruthy()
  })

  it('never renders a mid-flow single-choice button at 8-11, even under StrictMode double-invoke', () => {
    render(
      <StrictModeWrapper>
        <Reader story={flowToBranchStory} profileId="p1" ageBand="8-11" />
      </StrictModeWrapper>
    )
    expect(screen.queryByTestId('choice-c_enter')).toBeNull()
    expect(screen.queryByTestId('choice-c_walk')).toBeNull()
    expect(screen.getByTestId('choice-c_left')).toBeTruthy()
  })

  it("does not double-apply a flowed run under StrictMode's double-invoked mount effect", () => {
    vi.mocked(choose).mockClear()
    render(
      <StrictModeWrapper>
        <Reader story={flowToBranchStory} profileId="p1" ageBand="8-11" />
      </StrictModeWrapper>
    )
    // `choose()` is called twice by composeStop's own internal walk (a pure
    // preview: n_start->n_hall, n_hall->n_gallery) plus twice more by the
    // hook's silent CHOOSE batch that makes the real engine state catch up
    // to match -- four calls total for one genuine stop. A StrictMode
    // double-invoke without the hook's dedup guard would double that to
    // eight, silently walking the engine twice as far as the child actually
    // saw and double-applying n_hall's on_enter effect.
    expect(vi.mocked(choose)).toHaveBeenCalledTimes(4)
  })

  it('flows all the way into an ending with no intermediate Continue screen', () => {
    render(
      <MemoryRouter>
        <Reader story={flowToEndingStory} profileId="p1" ageBand="10-13" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_take_key'))
    // n_vestibule's single choice (condition true on has_key) flows straight
    // through to the ending; the reader lands on the ending screen directly.
    expect(screen.getByTestId('ending-screen')).toBeTruthy()
    expect(screen.queryByTestId('choice-c_locked_door')).toBeNull()
  })

  it('stops at a dead end rather than auto-flowing a false-condition choice', () => {
    render(
      <MemoryRouter>
        <Reader story={flowToEndingStory} profileId="p1" ageBand="10-13" />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('choice-c_skip_key'))
    // Without the key, n_vestibule's one choice is condition-gated false: the
    // stop ends there with no visible choices, not stuck mid-flow either.
    expect(screen.getByTestId('passage-body').textContent).toContain('locked door')
    expect(screen.queryByRole('button', { name: /unlock/i })).toBeNull()
  })

  it('halts a single-choice loop at the repeat rather than hanging or auto-looping forever', () => {
    render(
      <MemoryRouter>
        <Reader story={loopStory} profileId="p1" ageBand="8-11" />
      </MemoryRouter>
    )
    // The stop flows n_p -> n_q (both bodies render), then stops because
    // n_q's only choice would revisit n_p, already in this stop. That choice
    // (c_to_p) is still manually tappable -- the loop guard only stops
    // AUTO-flow, per stops.ts's documented semantics -- it just never
    // triggers on its own.
    const body = screen.getByTestId('passage-body').textContent ?? ''
    expect(body).toContain('marked Q')
    expect(body).toContain('marked P')
    expect(screen.getByTestId('choice-c_to_p')).toBeTruthy()
  })

  it("go back at a flowed band rewinds the whole stop, landing back on the previous stop's own choice, not mid-flow", () => {
    render(
      <MemoryRouter>
        <Reader story={flowToBranchStory} profileId="p1" ageBand="8-11" />
      </MemoryRouter>
    )
    // Page one: nothing precedes the very first stop.
    expect(screen.queryByTestId('go-back')).toBeNull()
    fireEvent.click(screen.getByTestId('choice-c_left'))
    expect(screen.getByTestId('ending-screen')).toBeTruthy()
    fireEvent.click(screen.getByTestId('go-back'))
    // Lands back on n_gallery, the previous stop's own real choice point
    // (ADR-026 decision 3): its full choice set is restored so the child can
    // pick differently, and never anything mid-flow (e.g. n_hall alone with
    // no choices to make).
    const body = screen.getByTestId('passage-body').textContent ?? ''
    expect(body).toContain('two wings')
    expect(screen.getByTestId('choice-c_left')).toBeTruthy()
    expect(screen.getByTestId('choice-c_right')).toBeTruthy()
  })

  it("go back from a multi-node stop lands on the PREVIOUS stop's own choice, not one node into it", () => {
    render(
      <MemoryRouter>
        <Reader story={backByStopStory} profileId="p1" ageBand="8-11" />
      </MemoryRouter>
    )
    // Stop 1: n_home flows into n_yard's branch.
    let body = screen.getByTestId('passage-body').textContent ?? ''
    expect(body).toContain('back door')
    expect(body).toContain('shed and a garden')
    expect(screen.getByTestId('choice-c_shed')).toBeTruthy()

    fireEvent.click(screen.getByTestId('choice-c_shed'))

    // Stop 2: n_tool flows into n_bench's branch.
    body = screen.getByTestId('passage-body').textContent ?? ''
    expect(body).toContain('full of tools')
    expect(body).toContain('workbench')
    expect(screen.getByTestId('choice-c_sit')).toBeTruthy()

    fireEvent.click(screen.getByTestId('go-back'))

    // Two BACK steps (stop 2 flowed two nodes) land exactly on n_yard, stop
    // 1's own real choice point -- never mid-flow on n_tool alone (which has
    // no choice of its own to offer, only a single silent hop).
    body = screen.getByTestId('passage-body').textContent ?? ''
    expect(body).toContain('shed and a garden')
    expect(body).not.toContain('full of tools')
    expect(screen.getByTestId('choice-c_shed')).toBeTruthy()
    expect(screen.getByTestId('choice-c_garden')).toBeTruthy()
  })

  it('still shows the dedication overlay on page one at a flowed band whose start node flows into a branch', () => {
    render(
      <MemoryRouter>
        <Reader
          story={flowToBranchStory}
          profileId="p1"
          ageBand="8-11"
          personalization={valuesPayload()}
        />
      </MemoryRouter>
    )
    expect(screen.getByTestId('dedication')).toBeTruthy()
  })

  it('shows a plain "Page N" position readout, counting stops not nodes, at a flowed band', () => {
    render(
      <MemoryRouter>
        <Reader story={flowToBranchStory} profileId="p1" ageBand="8-11" />
      </MemoryRouter>
    )
    // n_start+n_hall+n_gallery is one stop, so it is still page 1 even
    // though three nodes' worth of prose is on screen.
    expect(screen.getByTestId('reader-position').textContent).toBe('Page 1')
  })
})
