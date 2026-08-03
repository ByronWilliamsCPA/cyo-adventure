import { act, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ReadingHistoryItem } from '../client/types.gen'
import { EndingsProgress } from './EndingsProgress'

function historyRow(overrides: Partial<ReadingHistoryItem> = {}): ReadingHistoryItem {
  return {
    storybook_id: 's1',
    title: 'The Lantern',
    endings_found: 1,
    ending_ids: ['e1'],
    total_endings: 1,
    in_progress: false,
    last_activity_at: '2026-07-01T00:00:00Z',
    ...overrides,
  }
}

describe('EndingsProgress (K6, ending screen)', () => {
  it('shows the found-of-total copy once the lookup resolves for a multi-ending book', async () => {
    const fetchReadingHistory = vi
      .fn()
      .mockResolvedValue([historyRow({ endings_found: 3, total_endings: 7 })])
    render(
      <EndingsProgress profileId="p1" storybookId="s1" fetchReadingHistory={fetchReadingHistory} />
    )
    expect(
      await screen.findByText('You found ending 3 of 7! Read again to find more.')
    ).toBeInTheDocument()
    expect(fetchReadingHistory).toHaveBeenCalledWith('p1')
  })

  it('renders nothing for a book with only one ending', async () => {
    const fetchReadingHistory = vi
      .fn()
      .mockResolvedValue([historyRow({ endings_found: 1, total_endings: 1 })])
    const { container } = render(
      <EndingsProgress profileId="p1" storybookId="s1" fetchReadingHistory={fetchReadingHistory} />
    )
    await waitFor(() => expect(fetchReadingHistory).toHaveBeenCalled())
    expect(container.textContent).toBe('')
  })

  it('renders nothing when no row matches this storybook', async () => {
    const fetchReadingHistory = vi
      .fn()
      .mockResolvedValue([historyRow({ storybook_id: 'other-book', total_endings: 5 })])
    const { container } = render(
      <EndingsProgress profileId="p1" storybookId="s1" fetchReadingHistory={fetchReadingHistory} />
    )
    await waitFor(() => expect(fetchReadingHistory).toHaveBeenCalled())
    expect(container.textContent).toBe('')
  })

  it('renders nothing when the lookup fails (best-effort)', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const fetchReadingHistory = vi.fn().mockRejectedValue(new Error('boom'))
    const { container } = render(
      <EndingsProgress profileId="p1" storybookId="s1" fetchReadingHistory={fetchReadingHistory} />
    )
    await waitFor(() => expect(fetchReadingHistory).toHaveBeenCalled())
    expect(container.textContent).toBe('')
    errorSpy.mockRestore()
  })

  it('renders nothing before the lookup resolves', () => {
    const fetchReadingHistory = vi.fn().mockReturnValue(new Promise(() => {}))
    const { container } = render(
      <EndingsProgress profileId="p1" storybookId="s1" fetchReadingHistory={fetchReadingHistory} />
    )
    expect(container.textContent).toBe('')
  })

  it('discards a stale fetch from a previous storybook so it cannot over-report on the current one', async () => {
    // #ASSUME: timing dependencies: a stale fetch from a previously-viewed
    // storybook must never overwrite the current book's ending count with a
    // higher (numerically impossible) value; under-reporting (a slow fetch that
    // beats the completion POST) is the accepted failure mode, over-reporting is
    // not. EndingsProgress.tsx's effect-cleanup cancelled-guard enforces this.
    // #VERIFY: this test asserts the slow s1 fetch resolves only after the s2
    // rerender and is dropped, so the rendered count never rises to s1's total.
    let resolveFirst: (books: ReadingHistoryItem[]) => void = () => {}
    const firstFetch = new Promise<ReadingHistoryItem[]>((resolve) => {
      resolveFirst = resolve
    })
    const fetchReadingHistory = vi
      .fn()
      .mockReturnValueOnce(firstFetch)
      .mockResolvedValueOnce([
        historyRow({ storybook_id: 's2', endings_found: 1, total_endings: 2 }),
      ])

    const { rerender } = render(
      <EndingsProgress profileId="p1" storybookId="s1" fetchReadingHistory={fetchReadingHistory} />
    )
    rerender(
      <EndingsProgress profileId="p1" storybookId="s2" fetchReadingHistory={fetchReadingHistory} />
    )

    expect(
      await screen.findByText('You found ending 1 of 2! Read again to find more.')
    ).toBeInTheDocument()

    // The stale s1 fetch finally resolves with a count that would be
    // impossible for s2 (5 exceeds s2's total_endings of 2). It must be
    // discarded, not rendered.
    await act(async () => {
      resolveFirst([historyRow({ storybook_id: 's1', endings_found: 5, total_endings: 6 })])
      await Promise.resolve()
    })

    expect(
      screen.getByText('You found ending 1 of 2! Read again to find more.')
    ).toBeInTheDocument()
  })

  it('shows milestone framing (no denominator) above the threshold via the fallback lookup', async () => {
    const fetchReadingHistory = vi
      .fn()
      .mockResolvedValue([historyRow({ endings_found: 3, total_endings: 232 })])
    render(
      <EndingsProgress profileId="p1" storybookId="s1" fetchReadingHistory={fetchReadingHistory} />
    )
    expect(
      await screen.findByText("You've found 3 endings so far. Lots more to find.")
    ).toBeInTheDocument()
    expect(screen.queryByText(/of 232/)).toBeNull()
  })

  it('shows the all-found celebration via the fallback lookup', async () => {
    const fetchReadingHistory = vi
      .fn()
      .mockResolvedValue([historyRow({ endings_found: 7, total_endings: 7 })])
    render(
      <EndingsProgress profileId="p1" storybookId="s1" fetchReadingHistory={fetchReadingHistory} />
    )
    expect(
      await screen.findByText('You found them ALL! All 7 endings are yours.')
    ).toBeInTheDocument()
  })

  it('re-fetches when the storybookId changes', async () => {
    const fetchReadingHistory = vi
      .fn()
      .mockResolvedValue([historyRow({ storybook_id: 's2', endings_found: 1, total_endings: 4 })])
    const { rerender } = render(
      <EndingsProgress profileId="p1" storybookId="s1" fetchReadingHistory={fetchReadingHistory} />
    )
    rerender(
      <EndingsProgress profileId="p1" storybookId="s2" fetchReadingHistory={fetchReadingHistory} />
    )
    await waitFor(() => expect(fetchReadingHistory).toHaveBeenCalledTimes(2))
    expect(
      await screen.findByText('You found ending 1 of 4! Read again to find more.')
    ).toBeInTheDocument()
  })
})

describe('EndingsProgress completionOutcome (W0.3)', () => {
  it('renders nothing and does not fetch while the outcome is pending', () => {
    const fetchReadingHistory = vi.fn().mockReturnValue(new Promise(() => {}))
    const { container } = render(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{ status: 'pending' }}
      />
    )
    expect(container.textContent).toBe('')
    expect(fetchReadingHistory).not.toHaveBeenCalled()
  })

  it('renders the NEW-ending copy directly from a ready outcome, without fetching', async () => {
    const fetchReadingHistory = vi.fn().mockResolvedValue([])
    render(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{ status: 'ready', result: { is_new: true, found: 2, total: 4 } }}
      />
    )
    expect(
      await screen.findByText('You found a NEW ending! 2 of 4 found so far.')
    ).toBeInTheDocument()
    expect(fetchReadingHistory).not.toHaveBeenCalled()
  })

  it('renders the repeat-visit copy from a ready outcome when is_new is false', async () => {
    const fetchReadingHistory = vi.fn().mockResolvedValue([])
    render(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{ status: 'ready', result: { is_new: false, found: 3, total: 4 } }}
      />
    )
    expect(
      await screen.findByText('You found ending 3 of 4! Read again to find more.')
    ).toBeInTheDocument()
    expect(fetchReadingHistory).not.toHaveBeenCalled()
  })

  it('renders nothing for a ready outcome when total is 1 or fewer', async () => {
    const fetchReadingHistory = vi.fn().mockResolvedValue([])
    const { container } = render(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{ status: 'ready', result: { is_new: true, found: 1, total: 1 } }}
      />
    )
    await waitFor(() => expect(fetchReadingHistory).not.toHaveBeenCalled())
    expect(container.textContent).toBe('')
  })

  it('falls back to fetchReadingHistory when the outcome is unavailable (POST failed)', async () => {
    const fetchReadingHistory = vi
      .fn()
      .mockResolvedValue([historyRow({ endings_found: 2, total_endings: 4 })])
    render(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{ status: 'unavailable' }}
      />
    )
    expect(
      await screen.findByText('You found ending 2 of 4! Read again to find more.')
    ).toBeInTheDocument()
    expect(fetchReadingHistory).toHaveBeenCalledWith('p1')
  })

  it('falls back to the fetch when a ready result is malformed', async () => {
    // A 'ready' outcome without finite counts (stale mock, old server, a
    // proxy mangling the body) must never render "undefined of undefined";
    // it degrades to the same fallback as 'unavailable'.
    const fetchReadingHistory = vi
      .fn()
      .mockResolvedValue([historyRow({ endings_found: 2, total_endings: 4 })])
    render(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{
          status: 'ready',
          result: { is_new: true } as unknown as import('../api/readerApi').CompletionResult,
        }}
      />
    )
    expect(
      await screen.findByText('You found ending 2 of 4! Read again to find more.')
    ).toBeInTheDocument()
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument()
  })

  it('shows the all-found celebration when this completion reaches every ending (W1.3a)', async () => {
    const fetchReadingHistory = vi.fn().mockResolvedValue([])
    render(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{ status: 'ready', result: { is_new: true, found: 4, total: 4 } }}
      />
    )
    expect(
      await screen.findByText('You found them ALL! All 4 endings are yours.')
    ).toBeInTheDocument()
  })

  it('shows milestone framing (no denominator) above the shared threshold for a NEW find (AL-028)', async () => {
    const fetchReadingHistory = vi.fn().mockResolvedValue([])
    render(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{ status: 'ready', result: { is_new: true, found: 3, total: 232 } }}
      />
    )
    expect(
      await screen.findByText("You found a NEW ending! That's 3 endings so far. Lots more to find.")
    ).toBeInTheDocument()
    expect(screen.queryByText(/of 232/)).toBeNull()
  })

  it('shows milestone framing for a repeat visit above the shared threshold', async () => {
    const fetchReadingHistory = vi.fn().mockResolvedValue([])
    render(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{ status: 'ready', result: { is_new: false, found: 5, total: 232 } }}
      />
    )
    expect(
      await screen.findByText("You've found 5 endings so far. Lots more to find.")
    ).toBeInTheDocument()
  })

  it('re-fetches once the outcome transitions from pending to unavailable', async () => {
    const fetchReadingHistory = vi
      .fn()
      .mockResolvedValue([historyRow({ endings_found: 1, total_endings: 2 })])
    const { rerender } = render(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{ status: 'pending' }}
      />
    )
    expect(fetchReadingHistory).not.toHaveBeenCalled()
    rerender(
      <EndingsProgress
        profileId="p1"
        storybookId="s1"
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={{ status: 'unavailable' }}
      />
    )
    expect(
      await screen.findByText('You found ending 1 of 2! Read again to find more.')
    ).toBeInTheDocument()
  })
})
