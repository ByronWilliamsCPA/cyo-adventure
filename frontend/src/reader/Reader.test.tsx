import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { choose } from '../player/engine'
import type { Storybook } from '../player/types'
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

type FetchReadingHistoryMock = (profileId: string) => Promise<ReadingHistoryItem[]>
type SubmitFlagMock = (params: SubmitFlagParams) => Promise<KidFlagCreatedView>

describe('Reader K6 endings tracker', () => {
  function reachLanternEnding(fetchReadingHistory?: FetchReadingHistoryMock) {
    render(
      <MemoryRouter>
        <Reader
          story={lantern}
          profileId="p1"
          fetchReadingHistory={fetchReadingHistory}
        />
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
    expect(
      await screen.findByTestId('endings-tracker')
    ).toHaveTextContent('You found ending 2 of 4! Read again to find more.')
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
    const fetchReadingHistory = vi.fn<FetchReadingHistoryMock>().mockRejectedValue(new Error('boom'))
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
    constructor(text: string) {
      this.text = text
    }
  }

  const speakMock = vi.fn()
  const cancelMock = vi.fn()

  function installSpeechSynthesis() {
    vi.stubGlobal('speechSynthesis', { speak: speakMock, cancel: cancelMock })
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
    expect(choicesUtterance.text).toBe(
      'Your choices are: Pick up the lantern., Walk inside.'
    )
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
})
