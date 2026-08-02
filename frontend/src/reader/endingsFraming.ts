/**
 * Shared endings-count framing (AL-028, W1.3).
 *
 * K6's "found N of M endings" replay motivator inverts at large M: a
 * finished read of a 232-ending book reports "1 of 232" (0.4%), and part of
 * the denominator is effectively unreachable by an ordinary reader (3,000
 * random reads in the adversarial review found only 94 of 232). Above a
 * threshold, a raw denominator stops being a legible motivator and both kid
 * surfaces that show an endings count -- the reader's ending screen
 * (`EndingsProgress`) and the library shelf card (`EndingsBadge`) -- must
 * switch to milestone framing at the SAME M, per AL-028's explicit
 * requirement that they "share the threshold so the ending screen and the
 * shelf never disagree". Both import this module rather than each
 * hard-coding their own number.
 */

/**
 * The shared threshold. Reuses `EndingsBadge`'s long-standing decorative-dot
 * cap (`MAX_DOTS`, unchanged in value) rather than inventing a second
 * number: a book whose dot row was already too wide to show is exactly the
 * book whose denominator is too large to be a legible motivator either.
 */
export const ENDINGS_MILESTONE_THRESHOLD = 10

/** Whether a book's ending count is large enough that AL-028's milestone
 * framing (no denominator) applies instead of the ordinary "N of M" copy. */
export function isLargeEndingCatalog(total: number): boolean {
  return total > ENDINGS_MILESTONE_THRESHOLD
}

/**
 * The all-found celebration line (W1.3a): reaching every ending in the book
 * is its own distinct, stable state once true, regardless of whether the
 * book is small (still shows "N of M" below the threshold) or large (shows
 * milestone framing below this point). Checked by the caller as `found >=
 * total`, so it takes priority over both.
 */
export function allEndingsFoundLine(total: number): string {
  return total === 1 ? 'You found them ALL!' : `You found them ALL! All ${total} endings are yours.`
}

/**
 * The ending-screen milestone line (AL-028) shown above the threshold: no
 * denominator, "so far" framing that reads as ongoing progress rather than a
 * near-zero fraction. `isNew` distinguishes a first find from a repeat
 * visit, matching the below-threshold copy's own is_new framing.
 */
export function milestoneLine(found: number, isNew: boolean): string {
  const foundWord = found === 1 ? '1 ending' : `${found} endings`
  return isNew
    ? `You found a NEW ending! That's ${foundWord} so far. Lots more to find.`
    : `You've found ${foundWord} so far. Lots more to find.`
}

/** The shelf badge's milestone text (AL-028): drops the dot row and the
 * denominator, "N endings found" only. */
export function milestoneBadgeText(found: number): string {
  return found === 1 ? '1 ending found' : `${found} endings found`
}
