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
import type { FoundEndingCard } from '../kid/progressApi'
import { isLargeEndingCatalog, milestoneBadgeText } from '../reader/endingsFraming'

const VALENCE_ICON: Record<string, string> = {
  positive: '★', // filled star
  neutral: '◆', // diamond
  // A negative-valence ending is framed kindly, never as a loss (K14): the
  // same warm heart every found ending gets, not a distinct "sad" icon.
  negative: '♥', // heart
}

function endingIcon(valence: string): string {
  return VALENCE_ICON[valence] ?? VALENCE_ICON.neutral
}

export interface EndingsGalleryProps {
  open: boolean
  onClose: () => void
  bookTitle: string
  totalEndings: number
  foundEndings: FoundEndingCard[]
}

export function EndingsGallery({
  open,
  onClose,
  bookTitle,
  totalEndings,
  foundEndings,
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
        {large ? (
          <p className="endings-gallery__milestone">{milestoneBadgeText(foundEndings.length)}</p>
        ) : null}
        <ul className="endings-gallery__grid">
          {foundEndings.map((ending) => (
            <li key={ending.ending_id} className="endings-gallery__card endings-gallery__card--found">
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
      </div>
    </Dialog>
  )
}
