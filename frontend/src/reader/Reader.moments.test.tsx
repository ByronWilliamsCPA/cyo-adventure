/**
 * The three reader moments: opening a book (title page), reaching an ending
 * ("Try a different choice", framing, rating), and choice text that scales
 * with the reader's text size.
 */

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import type { ReactNode } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { choose, start } from '../player/engine'
import type { ValuesPayload } from '../player/personalization'
import type { ReadingState, Storybook } from '../player/types'
import { runStory } from '../test/runStory'
import { ENDING_FRAMING } from './endingInvitation'
import { Reader } from './Reader'
import { ReaderEntryContext, type ReaderEntry } from './readerEntry'

const online = vi.hoisted(() => ({ value: true }))
vi.mock('../hooks/useOnlineStatus', () => ({ useOnlineStatus: () => online.value }))

const here = path.dirname(fileURLToPath(import.meta.url))
const lantern = (
  JSON.parse(
    readFileSync(path.resolve(here, '../../../schema/conformance/player_traces.json'), 'utf-8')
  ) as { traces: { story: Storybook }[] }
).traces[0].story

// A straight line: one choice per page, then a win. No fork anywhere.
const linearStory: Storybook = {
  schema_version: '2.0',
  id: 's_linear',
  version: 1,
  title: 'One Way Home',
  metadata: {},
  variables: [],
  start_node: 'n_1',
  nodes: [
    {
      id: 'n_1',
      body: 'Off you go.',
      is_ending: false,
      choices: [{ id: 'c_1', label: 'Walk', target: 'n_2' }],
    },
    {
      id: 'n_2',
      body: 'Nearly there.',
      is_ending: false,
      choices: [{ id: 'c_2', label: 'Walk more', target: 'n_end' }],
    },
    {
      id: 'n_end',
      body: 'Home.',
      is_ending: true,
      choices: [],
      ending: { id: 'e_home', kind: 'completion', valence: 'positive', title: 'Home Again' },
    },
  ],
}

const titledStory: Storybook = {
  ...linearStory,
  id: 's_titled',
  title: 'The Quest of {~HERO:Explorer~}',
}

function payload(): ValuesPayload {
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

function withEntry(entry: ReaderEntry, children: ReactNode) {
  return (
    <MemoryRouter>
      <ReaderEntryContext value={entry}>{children}</ReaderEntryContext>
    </MemoryRouter>
  )
}

const ROUTED: ReaderEntry = { titlePage: true, entry: null }

function tap(testId: string): void {
  fireEvent.click(screen.getByTestId(testId))
}

beforeEach(() => {
  vi.stubGlobal('scrollTo', vi.fn())
  online.value = true
  try {
    localStorage.clear()
  } catch {
    // storage unavailable: font scale falls back to default
  }
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Reader title page', () => {
  it('opens a fresh read on the title page, then Start lands on page one with focus', () => {
    render(withEntry(ROUTED, <Reader story={lantern} profileId="p1" />))
    expect(screen.getByRole('heading', { level: 1, name: 'The Lantern Cave' })).toBeTruthy()
    expect(screen.queryByTestId('passage-body')).toBeNull()
    tap('start-reading')
    expect(screen.queryByTestId('title-page')).toBeNull()
    const passage = screen.getByTestId('passage-body')
    expect(document.activeElement).toBe(passage)
    expect(screen.getByTestId('choice-c_take_lantern')).toBeTruthy()
  })

  it('resumes mid-book straight onto the saved page, with no title page', () => {
    const resumed = choose(lantern, start(lantern), 'c_take_lantern')
    render(withEntry(ROUTED, <Reader story={lantern} profileId="p1" initialReading={resumed} />))
    expect(screen.queryByTestId('title-page')).toBeNull()
    expect(screen.getByTestId('choice-c_dark_passage')).toBeTruthy()
  })

  it('treats a saved state still on page one as a fresh open', () => {
    render(
      withEntry(ROUTED, <Reader story={lantern} profileId="p1" initialReading={start(lantern)} />)
    )
    expect(screen.getByTestId('title-page')).toBeTruthy()
  })

  it('shows the title page on a flowed read persisted at its opening stop terminal', () => {
    // runStory's n_intro (one choice) flows into n_fork at 8-11; the mount
    // walk persists n_fork with path [n_intro, n_fork], never tapped.
    const persisted = choose(runStory, start(runStory), 'c_go')
    render(
      withEntry(
        ROUTED,
        <Reader story={runStory} profileId="p1" ageBand="8-11" initialReading={persisted} />
      )
    )
    expect(screen.getByTestId('title-page')).toBeTruthy()
    tap('start-reading')
    expect(screen.getByTestId('choice-c_left')).toBeTruthy()
  })

  it('does not treat the same state as an opening at a page band', () => {
    const persisted = choose(runStory, start(runStory), 'c_go')
    render(withEntry(ROUTED, <Reader story={runStory} profileId="p1" initialReading={persisted} />))
    expect(screen.queryByTestId('title-page')).toBeNull()
  })

  it('never shows a title page without the routed entry context', () => {
    render(
      <MemoryRouter>
        <Reader story={lantern} profileId="p1" />
      </MemoryRouter>
    )
    expect(screen.queryByTestId('title-page')).toBeNull()
    expect(screen.getByTestId('passage-body')).toBeTruthy()
  })

  it('resolves personalization in the title, never rendering a raw marker', () => {
    render(
      withEntry(ROUTED, <Reader story={titledStory} profileId="p1" personalization={payload()} />)
    )
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('The Quest of Maya')
  })

  it('strips the title marker to its generic word without a payload', () => {
    render(withEntry(ROUTED, <Reader story={titledStory} profileId="p1" />))
    const heading = screen.getByRole('heading', { level: 1 }).textContent ?? ''
    expect(heading).toBe('The Quest of Explorer')
    expect(heading).not.toContain('{~')
  })

  it('shows the shelf cover when one is known, and the letter tile otherwise', () => {
    const { unmount } = render(
      withEntry(
        { titlePage: true, entry: { coverUrl: 'https://covers.example/c.webp', rating: null } },
        <Reader story={lantern} profileId="p1" />
      )
    )
    expect(screen.getByTestId('book-cover').querySelector('img')?.getAttribute('src')).toBe(
      'https://covers.example/c.webp'
    )
    unmount()
    render(withEntry(ROUTED, <Reader story={lantern} profileId="p1" />))
    expect(screen.getByTestId('book-cover').querySelector('img')).toBeNull()
    expect(screen.getByTestId('book-cover').textContent).toBe('T')
  })

  it('offers Leave and the text size control on the title page', () => {
    render(withEntry(ROUTED, <Reader story={lantern} profileId="p1" />))
    expect(screen.getByRole('button', { name: /Leave/ })).toBeTruthy()
    expect(screen.getByRole('radiogroup', { name: 'Text size' })).toBeTruthy()
  })
})

function playTo(choiceIds: string[]): void {
  for (const id of choiceIds) tap(`choice-${id}`)
}

describe('Reader "Try a different choice"', () => {
  it("lands on the fork before a single-choice run, with the run's effects undone", () => {
    const onProgress = vi.fn<(reading: ReadingState) => void>()
    render(withEntry(ROUTED, <Reader story={runStory} profileId="p1" onProgress={onProgress} />))
    tap('start-reading')
    playTo(['c_go', 'c_left', 'c_a1', 'c_a2'])
    expect(screen.getByTestId('ending-id').textContent).toBe('e_trap')
    tap('try-different-choice')
    expect(screen.queryByTestId('ending-screen')).toBeNull()
    expect(screen.getByTestId('choice-c_left')).toBeTruthy()
    expect(screen.getByTestId('choice-c_right')).toBeTruthy()
    const last = onProgress.mock.calls[onProgress.mock.calls.length - 1]?.[0]
    expect(last?.current_node).toBe('n_fork')
    expect(last?.path).toEqual(['n_intro', 'n_fork'])
    expect(last?.var_state).toEqual({ steps: 0 })
    expect(last?.visit_set).not.toContain('n_a1')
    const note = screen.getByTestId('rewind-note')
    expect(note.textContent).toContain('The red door')
    expect(document.activeElement).toBe(note)
  })

  it('clears the rewind note once the child chooses again', () => {
    render(withEntry(ROUTED, <Reader story={runStory} profileId="p1" />))
    tap('start-reading')
    playTo(['c_go', 'c_left', 'c_a1', 'c_a2'])
    tap('try-different-choice')
    tap('choice-c_right')
    expect(screen.getByTestId('ending-id').textContent).toBe('e_win')
    // Read again restarts at the beginning, the fork note does not come back.
    tap('restart')
    playTo(['c_go'])
    expect(screen.queryByTestId('rewind-note')).toBeNull()
  })

  it('rewinds a whole flowed run at 8-11 and lands on the fork stop', () => {
    render(withEntry(ROUTED, <Reader story={runStory} profileId="p1" ageBand="8-11" />))
    tap('start-reading')
    // The opening stop flows n_intro into n_fork; c_left flows a1, a2 and
    // the trap into one ending stop.
    tap('choice-c_left')
    expect(screen.getByTestId('ending-id').textContent).toBe('e_trap')
    tap('try-different-choice')
    expect(screen.getByTestId('choice-c_left')).toBeTruthy()
    expect(screen.getByTestId('choice-c_right')).toBeTruthy()
    // The fork stop is shown whole, with the prose that led into it.
    expect(screen.getByTestId('passage-body').textContent).toContain('You step into the hall.')
    expect(screen.getByTestId('passage-body').textContent).toContain('Two doors.')
  })

  it('counts only visible choices: skips a fork whose other choice was hidden', () => {
    render(withEntry(ROUTED, <Reader story={lantern} profileId="p1" />))
    tap('start-reading')
    playTo(['c_ignore_lantern', 'c_bright_tunnel'])
    tap('try-different-choice')
    expect(screen.getByTestId('choice-c_take_lantern')).toBeTruthy()
    expect(screen.getByTestId('choice-c_ignore_lantern')).toBeTruthy()
  })

  it('is hidden when the read had no earlier fork', () => {
    render(withEntry(ROUTED, <Reader story={linearStory} profileId="p1" />))
    tap('start-reading')
    playTo(['c_1', 'c_2'])
    expect(screen.getByTestId('ending-screen')).toBeTruthy()
    expect(screen.queryByTestId('try-different-choice')).toBeNull()
    // Read again keeps the primary slot when there is nothing to rewind to.
    expect(screen.getByTestId('restart').className).toContain('cyo-btn--primary')
  })

  it('leads a setback ending: primary, ahead of Read again, with setback framing', () => {
    render(withEntry(ROUTED, <Reader story={runStory} profileId="p1" />))
    tap('start-reading')
    playTo(['c_go', 'c_left', 'c_a1', 'c_a2'])
    const tryButton = screen.getByTestId('try-different-choice')
    const readAgain = screen.getByTestId('restart')
    expect(tryButton.className).toContain('cyo-btn--primary')
    expect(readAgain.className).toContain('cyo-btn--ghost')
    expect(
      tryButton.compareDocumentPosition(readAgain) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
    expect(screen.getByTestId('ending-framing').textContent).toBe(ENDING_FRAMING.capture)
  })

  it('stays secondary on a positive ending', () => {
    render(withEntry(ROUTED, <Reader story={lantern} profileId="p1" />))
    tap('start-reading')
    playTo(['c_take_lantern', 'c_dark_passage'])
    expect(screen.getByTestId('try-different-choice').className).toContain('cyo-btn--ghost')
    expect(screen.getByTestId('restart').className).toContain('cyo-btn--primary')
    expect(screen.getByTestId('ending-framing').textContent).toBe(ENDING_FRAMING.success)
  })

  it('shows the book title on the ending screen', () => {
    render(withEntry(ROUTED, <Reader story={lantern} profileId="p1" />))
    tap('start-reading')
    playTo(['c_take_lantern', 'c_dark_passage'])
    expect(screen.getByTestId('ending-book').textContent).toContain('The Lantern Cave')
  })

  it('leaves Go back a page exactly one page', () => {
    render(withEntry(ROUTED, <Reader story={runStory} profileId="p1" />))
    tap('start-reading')
    playTo(['c_go', 'c_left', 'c_a1', 'c_a2'])
    tap('go-back')
    expect(screen.getByTestId('passage-body').textContent).toContain('It gets darker.')
  })
})

describe('Reader ending rating', () => {
  function reachEnding(entry: ReaderEntry): void {
    render(withEntry(entry, <Reader story={lantern} profileId="p1" />))
    tap('start-reading')
    playTo(['c_take_lantern', 'c_dark_passage'])
  }

  function pressed(): string | null {
    const on = screen.getByTestId('ending-rating').querySelector('button[aria-pressed="true"]')
    return on?.getAttribute('aria-label') ?? null
  }

  it('shows the current rating and saves a change through the rating port', async () => {
    const rate = vi.fn((_id: string, value: number) => Promise.resolve(value))
    reachEnding({ titlePage: true, entry: { coverUrl: null, rating: 3 }, rate })
    expect(pressed()).toBe('Rate 3 stars')
    expect(screen.getByRole('group', { name: 'Rate The Lantern Cave' })).toBeTruthy()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Rate 5 stars' }))
      await Promise.resolve()
    })
    expect(rate).toHaveBeenCalledWith('s_lantern_cave', 5)
    expect(pressed()).toBe('Rate 5 stars')
  })

  it('keeps the previous rating when the save fails', async () => {
    const rate = vi.fn(() => Promise.reject(new Error('offline')))
    vi.spyOn(console, 'error').mockImplementation(() => {})
    reachEnding({ titlePage: true, entry: { coverUrl: null, rating: 2 }, rate })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Rate 4 stars' }))
      await Promise.resolve()
    })
    expect(pressed()).toBe('Rate 2 stars')
  })

  it('never blocks the other ending actions while a save is pending', () => {
    const rate = vi.fn(() => new Promise<number>(() => {}))
    reachEnding({ titlePage: true, entry: null, rate })
    fireEvent.click(screen.getByRole('button', { name: 'Rate 4 stars' }))
    tap('try-different-choice')
    expect(screen.getByTestId('choice-c_dark_passage')).toBeTruthy()
  })

  it('is withheld offline, like the offline shelf', () => {
    online.value = false
    reachEnding({ titlePage: true, entry: null, rate: vi.fn() })
    expect(screen.queryByTestId('ending-rating')).toBeNull()
    expect(screen.getByTestId('restart')).toBeTruthy()
  })

  it('is absent without a rating port', () => {
    reachEnding(ROUTED)
    expect(screen.queryByTestId('ending-rating')).toBeNull()
  })
})

describe('Reader choice text size', () => {
  it('applies the reader font scale to the subtree the choices render in', () => {
    render(withEntry(ROUTED, <Reader story={lantern} profileId="p1" />))
    tap('start-reading')
    fireEvent.click(screen.getByRole('radio', { name: 'Text size A++' }))
    const choice = screen.getByTestId('choice-c_take_lantern')
    const shell = choice.closest<HTMLElement>('.reader-shell')
    expect(shell?.style.getPropertyValue('--reader-font-scale')).toBe('1.3')
  })

  it('sizes ChoiceButton from the same band and scale properties as the passage', () => {
    // jsdom does not evaluate calc() on custom properties, so pin the rule
    // itself: the choice font-size must be the passage's expression.
    const css = readFileSync(
      path.resolve(here, '../../design-system/src/components/ChoiceButton/ChoiceButton.css'),
      'utf-8'
    )
    expect(css).toContain(
      'font-size: calc(var(--band-reader-text, var(--text-base)) * var(--reader-font-scale, 1));'
    )
    const readerCss = readFileSync(path.resolve(here, 'reader.css'), 'utf-8')
    expect(readerCss).toMatch(
      /\.reader \.cyo-passage,\s*\.reader-ending \.cyo-passage,\s*\.reader \.cyo-choice \{/
    )
  })
})
