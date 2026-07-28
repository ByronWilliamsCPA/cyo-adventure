/**
 * Pure word-boundary mapping for read-aloud highlighting (P-5: pre-reader
 * accessibility). `SpeechSynthesisUtterance`'s `onboundary` event reports a
 * `charIndex` into the utterance's own text, but browsers disagree on
 * whether that index lands exactly on a word's first letter or on
 * preceding whitespace/punctuation, so this walks forward past any
 * whitespace before measuring the word's extent.
 *
 * Kept pure and free of the DOM/Web Speech API on purpose: jsdom (and the
 * Playwright mocked tier's fake `speechSynthesis`) does not fire real
 * `onboundary` events with realistic timing, so the position-to-word mapping
 * is unit-tested directly here (readAloudHighlight.test.ts), while
 * useReadAloud.test.ts separately verifies the hook advances its exposed
 * state when a synthetic boundary event is dispatched.
 */

export interface WordRange {
  /** Inclusive start offset, in UTF-16 code units, into the source text. */
  start: number
  /** Exclusive end offset. */
  end: number
}

/**
 * Given the text an utterance was constructed from and a `charIndex`
 * reported by its `onboundary` word event, return the `[start, end)` range
 * of the word currently being spoken.
 *
 * Returns null when the index falls outside the text, or lands in trailing
 * whitespace with no word after it.
 * #EDGE: timing: a stale event racing a `stop()`/new `speak()` call, or a
 * `charIndex` a browser reports against a slightly different string (a
 * normalization quirk), can hand back an out-of-range index; treating that
 * as "no highlight" is the safe degrade rather than throwing mid-story.
 * #VERIFY: readAloudHighlight.test.ts covers an index at, before, and past
 * text length, and an index that lands inside whitespace.
 */
export function wordRangeAtIndex(text: string, charIndex: number): WordRange | null {
  if (!Number.isFinite(charIndex) || charIndex < 0 || charIndex >= text.length) {
    return null
  }
  let start = charIndex
  while (start < text.length && /\s/.test(text[start])) {
    start += 1
  }
  if (start >= text.length) {
    return null
  }
  let end = start
  while (end < text.length && !/\s/.test(text[end])) {
    end += 1
  }
  return { start, end }
}
