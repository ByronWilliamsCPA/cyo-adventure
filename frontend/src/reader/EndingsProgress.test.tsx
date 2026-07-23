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
