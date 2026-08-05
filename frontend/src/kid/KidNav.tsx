import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'

import { AvatarCircle } from '../profiles/AvatarCircle'
import { useApi } from '../hooks/useApi'
import { BadgeCase } from './BadgeCase'
import { EMPTY_PROGRESS, makeProgressApi, type ProgressSummary } from './progressApi'
import { useKidProfile } from './useKidProfile'
import { WeeklyRing } from './WeeklyRing'
import { GUARDIAN_LOGIN_PATH, KID_PICKER_PATH } from '../routes'

export interface KidNavProps {
  /** The profile whose library/story is on screen. */
  profileId: string
}

// #ASSUME: browser-compat: jsdom (and some locked-down browsers) can lack
// matchMedia entirely; a missing API reads as "no reduced-motion
// preference" rather than throwing, matching Reader.tsx's own guard for the
// identical media query.
function prefersReducedMotionOS(): boolean {
  return (
    typeof window !== 'undefined' &&
    Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
  )
}

/**
 * Persistent kid wayfinding bar (the "easy to navigate" fix). The kid surface
 * previously had no chrome at all, so once a child reached their library there
 * was no visible way back. This bar sits above the library and always offers a
 * way to switch readers, and shows whose books these are.
 *
 * W3.4/W3.2: also the shell-header home for the weekly reading-days ring and
 * the badge-case entry point (gamification recommendation section 3: "the
 * weekly ring, small, in the shell header" / "badge case ... off the
 * library or KidShell nav"). Both are driven by one best-effort
 * `GET /me/progress` fetch and hidden entirely -- not shown disabled, not
 * shown empty -- whenever their resolved settings are off, per K14 (nothing
 * punitive ever appears, not even an off switch's shadow).
 *
 * The child's name/avatar is a best-effort touch (see useKidProfile); a
 * failure (offline, hiccup) degrades to the generic "Switch reader" control
 * rather than blocking the page.
 *
 * Also carries a persistent, low-key "Ask a grown-up" link to
 * `/guardian/login` (product decision, 2026-08-04). Paths from the kid surface
 * toward the guardian side already existed, but every one of them surfaced only
 * in a degraded state: ProfilePickerPage's unauthenticated, forbidden, and
 * load-error tiles, its PIN-failure escape hatch after three attempts, and
 * LibraryPage's and ReaderPage's own unauthenticated states. On a
 * normally-working Library page a child had no always-available way to reach a
 * grown-up; this is the first persistent one.
 *
 * Scope: KidShell mounts KidNav on `/library/:profileId` only, so this link is
 * a Library-header affordance. The Reader route is unchanged and still returns
 * to Library via its own "Leave" control.
 *
 * This is a pure reachability fix, not a new door into the guardian console: it
 * goes to the same login route those existing escapes already use, so the
 * guardian still signs in and the AdultGate step-up still applies exactly as it
 * would from any other entry point.
 */
export function KidNav({ profileId }: KidNavProps) {
  const profile = useKidProfile(profileId)?.profile ?? null

  const rawApi = useApi()
  const progressApi = useMemo(() => makeProgressApi(rawApi, profileId), [rawApi, profileId])
  const [progress, setProgress] = useState<ProgressSummary>(EMPTY_PROGRESS)
  useEffect(() => {
    let cancelled = false
    progressApi
      .getProgress()
      .then((result) => {
        if (!cancelled) setProgress(result)
      })
      .catch((error: unknown) => {
        // Best-effort, decorative-only surface: a failed fetch just means
        // the ring/badge case stay hidden this visit, never an error shown
        // to the child.
        console.error('[kid] progress fetch failed', { profileId, error })
      })
    return () => {
      cancelled = true
    }
  }, [progressApi, profileId])

  const [badgeCaseOpen, setBadgeCaseOpen] = useState(false)
  const reduceMotion = Boolean(profile?.reduce_motion) || prefersReducedMotionOS()

  return (
    <nav className="kid-nav" aria-label="Reader navigation">
      <span className="kid-nav__who">
        {profile ? (
          <>
            <span className="kid-nav__avatar">
              <AvatarCircle avatar={profile.avatar} name={profile.display_name} />
            </span>
            <span className="kid-nav__label">
              <b>{profile.display_name}</b>
              <span>reading</span>
            </span>
          </>
        ) : (
          <span className="kid-nav__label">
            <b>My books</b>
          </span>
        )}
      </span>
      <span className="kid-nav__gamification">
        {/* Hidden entirely (no ring, no placeholder) when disabled -- band
            3-5 default-off, or a guardian's explicit off toggle. */}
        {progress.settings.ring_enabled ? (
          <WeeklyRing
            profileId={profileId}
            daysReadThisWeek={progress.days_read_this_week}
            goalDays={progress.settings.ring_goal_days}
            reduceMotion={reduceMotion}
          />
        ) : null}
        {progress.settings.badges_enabled ? (
          <button
            type="button"
            className="kid-nav__badges-button"
            data-testid="open-badge-case"
            onClick={() => setBadgeCaseOpen(true)}
          >
            Badges
          </button>
        ) : null}
      </span>
      <Link className="kid-nav__switch" to={KID_PICKER_PATH}>
        <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4 8 H16 L13 5 M20 16 H8 L11 19"
          />
        </svg>
        {/* Wrapped in a span so the LABEL can ellipsize at narrow widths
            while the glyph beside it stays full size; a bare text node is
            not styleable. See .kid-nav__switch-label in kid.css. */}
        <span className="kid-nav__switch-label">Switch reader</span>
      </Link>
      <Link className="kid-nav__ask-grownup" to={GUARDIAN_LOGIN_PATH}>
        Ask a grown-up
      </Link>
      {progress.settings.badges_enabled ? (
        <BadgeCase
          open={badgeCaseOpen}
          onClose={() => setBadgeCaseOpen(false)}
          earnedBadges={progress.badges}
        />
      ) : null}
    </nav>
  )
}
