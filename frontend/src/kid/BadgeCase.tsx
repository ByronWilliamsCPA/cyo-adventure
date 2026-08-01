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
              className={earned ? 'badge-case__card badge-case__card--earned' : 'badge-case__card badge-case__card--locked'}
            >
              <span className="badge-case__icon" aria-hidden="true">
                {earned ? '🏅' : '⭐'}
              </span>
              <span className="badge-case__name">{entry.name}</span>
              <span className="badge-case__hint">{entry.description}</span>
            </li>
          )
        })}
      </ul>
    </Dialog>
  )
}
