import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { choose } from '../player/engine'
import type { Storybook } from '../player/types'
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

  it('shows a full progress bar with a finished label at an ending', () => {
    reachLanternEnding()
    const bar = screen.getByRole('progressbar')
    // A finished story never looks unfinished, even though the all-nodes
    // denominator means a single playthrough cannot visit every node.
    expect(bar.getAttribute('aria-valuenow')).toBe('100')
    expect(bar.getAttribute('aria-label')).toBe('You finished this story!')
  })

  it('keeps the progress bar partial before the ending', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).not.toBe('100')
  })

  it('celebrates a positive ending with the animated stars', () => {
    reachLanternEnding()
    const stars = screen.getByTestId('ending-celebration')
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
