/**
 * Badge case (W3.2, gamification recommendation section 3): earned badges in
 * color, unearned as silhouettes with a kid-readable hint. Reachable off the
 * kid nav (KidNav.tsx), never off the profile picker (anti-leaderboard line,
 * P3): this screen only ever shows ONE child's own badges, mounted from a
 * context that already knows which profile is reading.
 *
 * Hidden entirely (not rendered at all, not shown-disabled) when the
 * guardian has turned badges off for this profile (`settings.badges_enabled`
 * resolved from `GET /me/progress`); the caller (KidNav) makes that call, so
 * this component itself has no "disabled" rendering branch to keep in sync.
 */

import { Dialog } from '@ds/components/Dialog'
import { BADGE_CATALOG } from './badgeCatalog'
import type { EarnedBadgeCard } from './progressApi'

export interface BadgeCaseProps {
  open: boolean
  onClose: () => void
  earnedBadges: EarnedBadgeCard[]
}

export function BadgeCase({ open, onClose, earnedBadges }: BadgeCaseProps) {
  if (!open) return null
  const earnedIds = new Set(earnedBadges.map((b) => b.id))
  // #ASSUME: data integrity: an earned badge whose id is NOT in the local
  // catalog must still appear, rendered from the server's own name and
  // description. Iterating BADGE_CATALOG alone silently dropped it, and the
  // child saw the sharpest possible contradiction: BadgeUnlockToast
  // celebrates "You earned X!" from `badge.name` on the wire, then X is
  // nowhere in the badge case a tap later.
  //
  // badgeCatalog.test.ts does NOT cover this. It parses `progress/badges.py`
  // and pins the catalogs id-for-id, which makes BUILD-time drift between two
  // files in one repo impossible. The pairing that actually fails is a
  // DEPLOYED server against a DEPLOYED client: this is a PWA with an offline
  // cache and a service worker, so a device can hold an older bundle than the
  // backend it is talking to for as long as the child does not get a fresh
  // install. A repo-internal lockstep test cannot see across that gap.
  // #VERIFY: BadgeCase.test.tsx "shows an earned badge the local catalog does
  // not know about".
  const catalogIds = new Set(BADGE_CATALOG.map((entry) => entry.id))
  const uncatalogued = earnedBadges.filter((badge) => !catalogIds.has(badge.id))
  return (
    <Dialog
      title="Your Badges"
      open={open}
      onClose={onClose}
      actions={
        <button type="button" className="cyo-button cyo-button--ghost" onClick={onClose}>
          Close
        </button>
      }
    >
      <ul className="badge-case__grid">
        {BADGE_CATALOG.map((entry) => {
          const earned = earnedIds.has(entry.id)
          return (
            <li
              key={entry.id}
              className={
                earned
                  ? 'badge-case__card badge-case__card--earned'
                  : 'badge-case__card badge-case__card--locked'
              }
            >
              <span className="badge-case__icon" aria-hidden="true">
                {earned ? '🏅' : '⭐'}
              </span>
              <span className="badge-case__name">{entry.name}</span>
              {/* Earned/locked was previously carried ONLY by the card's
                  colour and a decorative aria-hidden emoji, so a screen
                  reader read an earned and an unearned badge identically,
                  and a colourblind child had only saturation to go on.
                  Visible text rather than an aria-label on the <li>: an
                  aria-label would override the name and hint underneath it,
                  trading one lost fact for two. Mirrors EndingsGallery's
                  "Still hidden" tile. */}
              <span className="badge-case__state">{earned ? 'Earned!' : 'Not yet'}</span>
              <span className="badge-case__hint">{entry.description}</span>
            </li>
          )
        })}
        {/* Always earned by construction (they came from the earned list), so
            no locked variant and no state ternary. Rendered after the roster
            rather than merged into it: their position in the server's badge
            order means nothing to the catalog's deliberate ordering. */}
        {uncatalogued.map((badge) => (
          <li key={badge.id} className="badge-case__card badge-case__card--earned">
            <span className="badge-case__icon" aria-hidden="true">
              🏅
            </span>
            <span className="badge-case__name">{badge.name}</span>
            <span className="badge-case__state">Earned!</span>
            <span className="badge-case__hint">{badge.description}</span>
          </li>
        ))}
      </ul>
    </Dialog>
  )
}
