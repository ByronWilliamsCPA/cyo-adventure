/**
 * Weekly reading-days ring (W3.4, gamification recommendation section 2.3 /
 * design review P-A). Shows days read this week toward the resolved
 * per-band goal (server-resolved: see `kid/progressApi.ts`'s
 * `ResolvedGamificationSettings`, never re-derived here). Days only, never
 * minutes (P4): the kid client is not even handed a minutes figure.
 *
 * K14 / P2 (celebrate, never punish): an unfilled or lapsed week renders
 * NOTHING negative -- no gray "almost" state, no reset copy, no reminder.
 * Filling the ring triggers a one-time-per-week celebration (a still mascot
 * moment, or an animated one when neither reduce-motion signal is set); a
 * child who already saw this week's celebration (tracked in localStorage,
 * mirroring `useReaderFontScale`'s own per-profile preference storage) never
 * sees it fire twice for the same week.
 *
 * Visibility (hidden entirely) is the CALLER's decision, driven by the
 * resolved `ring_enabled` flag -- this component always renders its dots
 * once mounted, per its own doc above; it does not re-check `ring_enabled`
 * itself, so mounting it IS choosing to show it (KidNav gates the mount).
 */

import { useEffect } from 'react'

function mondayOf(date: Date): Date {
  const day = date.getDay() // 0 = Sunday
  const diffToMonday = day === 0 ? -6 : 1 - day
  const monday = new Date(date)
  monday.setDate(date.getDate() + diffToMonday)
  monday.setHours(0, 0, 0, 0)
  return monday
}

function weekKey(date: Date): string {
  const monday = mondayOf(date)
  const year = monday.getFullYear()
  const month = String(monday.getMonth() + 1).padStart(2, '0')
  const day = String(monday.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function celebrationStorageKey(profileId: string, weekOf: string): string {
  return `cyo-ring-celebrated-${profileId}-${weekOf}`
}

/** Whether this device has already recorded this week's celebration for this
 * profile. A read-only, best-effort localStorage check performed directly
 * during render (mirrors `useReaderFontScale.ts::readLevel`'s own accepted
 * render-time read); storage failures (private mode) degrade to "not yet
 * celebrated" rather than throwing. */
function hasCelebratedThisWeek(profileId: string, weekOf: string): boolean {
  try {
    return localStorage.getItem(celebrationStorageKey(profileId, weekOf)) === '1'
  } catch {
    return false
  }
}

/** Marks this (profile, week) as celebrated, so it never fires again on this
 * device. The one-time-per-week celebration's ONLY side effect on an
 * external system (localStorage), so it belongs in an effect; it
 * deliberately never calls setState -- `WeeklyRing` derives `shouldCelebrate`
 * straight from `hasCelebratedThisWeek` during render instead, so there is
 * no derived-state effect to trigger a cascading re-render. */
function useRecordWeeklyCelebration(profileId: string, weekOf: string, shouldCelebrate: boolean): void {
  useEffect(() => {
    if (!shouldCelebrate) return
    try {
      localStorage.setItem(celebrationStorageKey(profileId, weekOf), '1')
    } catch {
      // Best-effort only; see the function doc above.
    }
  }, [profileId, weekOf, shouldCelebrate])
}

export interface WeeklyRingProps {
  profileId: string
  daysReadThisWeek: number
  goalDays: number
  /** Either reduce-motion signal (guardian-set profile preference OR the
   * OS-level `prefers-reduced-motion` media query) stills the celebration
   * animation; the caller folds both into one boolean (mirrors Reader.tsx's
   * own `reduceMotion` computation for the passage-scroll animation). */
  reduceMotion: boolean
  /** Injectable clock for deterministic tests. Defaults to `() => new Date()`. */
  now?: () => Date
}

export function WeeklyRing({
  profileId,
  daysReadThisWeek,
  goalDays,
  reduceMotion,
  now = () => new Date(),
}: WeeklyRingProps) {
  const clampedGoal = Math.max(1, goalDays)
  const clampedDays = Math.max(0, Math.min(daysReadThisWeek, clampedGoal))
  const filled = clampedDays >= clampedGoal
  const currentWeek = weekKey(now())
  const celebrate = filled && !hasCelebratedThisWeek(profileId, currentWeek)
  useRecordWeeklyCelebration(profileId, currentWeek, celebrate)

  const radius = 16
  const circumference = 2 * Math.PI * radius
  const fraction = clampedDays / clampedGoal
  const dashoffset = circumference * (1 - fraction)

  return (
    <div
      className={
        celebrate && !reduceMotion
          ? 'weekly-ring weekly-ring--celebrate'
          : 'weekly-ring'
      }
      data-testid="weekly-ring"
      role="img"
      aria-label={
        clampedDays === 1
          ? `You read on 1 day this week, out of a goal of ${clampedGoal}`
          : `You read on ${clampedDays} days this week, out of a goal of ${clampedGoal}`
      }
    >
      <svg width="36" height="36" viewBox="0 0 36 36" aria-hidden="true">
        <circle
          cx="18"
          cy="18"
          r={radius}
          fill="none"
          stroke="var(--color-ring-track, #e8d9c3)"
          strokeWidth="4"
        />
        <circle
          cx="18"
          cy="18"
          r={radius}
          fill="none"
          stroke="var(--color-ring-fill, #e07f2e)"
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashoffset}
          transform="rotate(-90 18 18)"
        />
      </svg>
      <span className="weekly-ring__days" aria-hidden="true">
        {clampedDays}
      </span>
    </div>
  )
}
