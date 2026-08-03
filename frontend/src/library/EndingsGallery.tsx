/**
 * Endings Gallery (W3.2, gamification recommendation section 2.1): a
 * per-book collectible-card screen, reachable from the book card and the
 * ending screen. Found endings render as real cards (title, valence-aware
 * icon); unfound endings render as generic "still hidden" silhouettes --
 * never a real title or id, so a child can never learn an ending's name
 * before finding it.
 *
 * Large-M honesty (AL-028): above `ENDINGS_MILESTONE_THRESHOLD`
 * (reader/endingsFraming.ts, shared with the ending screen's own tracker and
 * the shelf badge so all three never disagree), the silhouette grid is
 * dropped entirely in favor of milestone framing -- a 232-ending book never
 * renders 200+ gray placeholder tiles.
 */

import { Dialog } from '@ds/components/Dialog'
import type { Valence } from '../client'
import type { FoundEndingCard } from '../kid/progressApi'
import { isLargeEndingCatalog, milestoneBadgeText } from '../reader/endingsFraming'

// Keyed by the GENERATED `Valence` union, not `string`. The backend now
// declares FoundEndingView.valence as that closed enum, so a member added
// there (and picked up by the next client regeneration) fails typecheck here
// until this table gains an icon, rather than silently falling through to the
// diamond for every ending of the new kind. The runtime fallback below stays
// regardless: this record types the CONTRACT, and progressApi deliberately
// does not validate the string that actually arrives.
const VALENCE_ICON: Record<Valence, string> = {
  positive: '★', // filled star
  neutral: '◆', // diamond
  // A negative-valence ending is framed kindly, never as a loss (K14): the
  // same warm heart every found ending gets, not a distinct "sad" icon.
  negative: '♥', // heart
}

function endingIcon(valence: string): string {
  // #EDGE: data integrity: `valence` is untyped wire data here (progressApi's
  // FoundEndingCard widens it to `string` on purpose, matching how that
  // adapter degrades every other malformed field rather than throwing), so
  // the lookup can still miss. Falling back to the neutral diamond keeps a
  // corrupt ending as a real, readable card instead of a blank icon slot.
  // #VERIFY: EndingsGallery.test.tsx "falls back to the neutral icon for an
  // unrecognized valence".
  return VALENCE_ICON[valence as Valence] ?? VALENCE_ICON.neutral
}

export interface EndingsGalleryProps {
  open: boolean
  onClose: () => void
  bookTitle: string
  totalEndings: number
  foundEndings: FoundEndingCard[]
  /**
   * The caller could not load this book's collection state at all, as
   * distinct from loading it and finding nothing collected yet. Renders a
   * "could not load" line instead of the empty-state copy.
   *
   * #ASSUME: data-integrity: without this, a failed fetch is indistinguishable
   * from a genuinely empty collection, because both arrive here as
   * `foundEndings: []`. `/v1/me/progress` is child-principal-only, so a
   * guardian previewing as their child gets a 403 and would otherwise read
   * "Keep reading to start finding endings!" on a book they just finished.
   * #VERIFY: EndingsGalleryButton.test.tsx "shows a could-not-load message
   * rather than the empty state when the progress fetch fails".
   */
  unavailable?: boolean
}

export function EndingsGallery({
  open,
  onClose,
  bookTitle,
  totalEndings,
  foundEndings,
  unavailable = false,
}: EndingsGalleryProps) {
  if (!open) return null
  const large = isLargeEndingCatalog(totalEndings)
  const hiddenCount = Math.max(0, totalEndings - foundEndings.length)
  return (
    <Dialog
      title={`${bookTitle}: Endings`}
      open={open}
      onClose={onClose}
      actions={
        <button type="button" className="cyo-button cyo-button--ghost" onClick={onClose}>
          Close
        </button>
      }
    >
      <div className="endings-gallery">
        {unavailable ? (
          <p className="endings-gallery__empty" data-testid="endings-gallery-unavailable">
            We could not load your endings right now. Try again in a bit!
          </p>
        ) : (
          <>
            {large ? (
              <p className="endings-gallery__milestone">
                {milestoneBadgeText(foundEndings.length)}
              </p>
            ) : null}
            <ul className="endings-gallery__grid">
              {foundEndings.map((ending) => (
                <li
                  key={ending.ending_id}
                  className="endings-gallery__card endings-gallery__card--found"
                >
                  <span className="endings-gallery__icon" aria-hidden="true">
                    {endingIcon(ending.valence)}
                  </span>
                  <span className="endings-gallery__card-title">{ending.title}</span>
                </li>
              ))}
              {/* Silhouette placeholders only below the large-M threshold: a huge
              catalog gets the milestone line above instead of a wall of
              gray tiles. */}
              {!large
                ? Array.from({ length: hiddenCount }, (_, index) => (
                    <li
                      key={`hidden-${index}`}
                      className="endings-gallery__card endings-gallery__card--hidden"
                      aria-label="Still hidden"
                    >
                      <span className="endings-gallery__icon" aria-hidden="true">
                        ?
                      </span>
                      <span className="endings-gallery__card-title">Still hidden</span>
                    </li>
                  ))
                : null}
            </ul>
            {foundEndings.length === 0 ? (
              <p className="endings-gallery__empty">Keep reading to start finding endings!</p>
            ) : null}
          </>
        )}
      </div>
    </Dialog>
  )
}
