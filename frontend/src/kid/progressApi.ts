/**
 * Adapter for `GET /v1/me/progress` (W3.1/W3.2/W3.4).
 *
 * Hand-typed like `storyStatusApi.ts`. The generated client
 * (`src/client/types.gen.ts` `ProgressView`) has since been regenerated and
 * carries the same wire shape; this adapter is retained for its narrowed
 * types and defensive fallbacks. Follow-up: assert parity against the
 * generated type in `apiContractParity.ts` (tracked in the wave PR notes).
 *
 * Mirrors `src/cyo_adventure/api/schemas.py`: `EarnedBadgeView`,
 * `FoundEndingView`, `BookProgressView`, `ProgressTotalsView`,
 * `ResolvedGamificationSettingsView`, `ProgressView`.
 */

import type { AxiosInstance } from 'axios'

export interface EarnedBadgeCard {
  id: string
  name: string
  description: string
  earned_at: string
}

export interface FoundEndingCard {
  ending_id: string
  title: string
  valence: string
}

export interface BookProgressCard {
  storybook_id: string
  title: string
  endings_found: number
  total_endings: number
  finished: boolean
  every_path_walked: boolean
  found_endings: FoundEndingCard[]
}

export interface ProgressTotalsCard {
  books_finished: number
  endings_found: number
}

/** Resolved gamification settings (W3.4): band defaults already applied
 * server-side, so this client never re-implements the P-A band table. */
export interface ResolvedGamificationSettings {
  ring_enabled: boolean
  ring_goal_days: number
  badges_enabled: boolean
  time_capture_paused: boolean
}

export interface ProgressSummary {
  badges: EarnedBadgeCard[]
  books: BookProgressCard[]
  totals: ProgressTotalsCard
  days_read_this_week: number
  lifetime_days_read: number
  settings: ResolvedGamificationSettings
}

// #ASSUME: data integrity: a CLIENT-SIDE fetch failure means this device
// simply does not know the real resolved settings yet, which is a stronger
// unknown than the backend's own missing-profile-row fallback (that one
// resolves to the YOUNGEST band's row, so it too fails closed on
// ring_enabled; see api/progress.py's _UNKNOWN_BAND).
// Failing closed (everything off/hidden) is the safe direction: showing a
// ring or badge case for a profile whose real band default is OFF (3-5)
// would be a visible K14/P-A violation, while hiding a ring that should be
// on is merely a missed decoration for one visit. ring_goal_days keeps a
// plausible value only because it is inert whenever ring_enabled is false.
// #VERIFY: kid/progressApi.test.ts "tolerates a malformed response";
// kid/KidNav.test.tsx "never shows the ring or badge case when the progress
// fetch fails".
const FALLBACK_SETTINGS: ResolvedGamificationSettings = {
  ring_enabled: false,
  ring_goal_days: 3,
  badges_enabled: false,
  time_capture_paused: false,
}

/**
 * Normalize the nested `settings` object field-by-field.
 *
 * The outer normalizer's `data.settings ?? FALLBACK_SETTINGS` only caught a
 * settings object that was absent entirely. A PARTIAL one (`{ring_enabled:
 * true}` from a stale mock or a mid-rollout contract change) passed straight
 * through, so `ring_goal_days` arrived `undefined`, `Math.max(1, undefined)`
 * evaluated to NaN, and WeeklyRing rendered `strokeDashoffset={NaN}` under an
 * aria-label reading "out of a goal of NaN". Every scalar at the top level was
 * already guarded this way; the nested object was the gap.
 *
 * Note the asymmetry that is deliberate: the two booleans fall back to FALSE
 * on a bad value, matching FALLBACK_SETTINGS' fail-closed posture (showing a
 * ring for a 3-5 reader whose band default is off is a visible K14 violation),
 * while `ring_goal_days` falls back to a plausible 3 because it is inert
 * whenever `ring_enabled` is false.
 */
function normalizeSettings(raw: unknown): ResolvedGamificationSettings {
  if (typeof raw !== 'object' || raw === null) return FALLBACK_SETTINGS
  const s = raw as Partial<ResolvedGamificationSettings>
  return {
    ring_enabled: s.ring_enabled === true,
    ring_goal_days:
      typeof s.ring_goal_days === 'number' && Number.isFinite(s.ring_goal_days)
        ? s.ring_goal_days
        : FALLBACK_SETTINGS.ring_goal_days,
    badges_enabled: s.badges_enabled === true,
    time_capture_paused: s.time_capture_paused === true,
  }
}

/** Same field-by-field treatment for the totals object, for the same reason:
 * a partial one rendered `undefined` into the kid-facing counts. */
function normalizeTotals(raw: unknown): ProgressTotalsCard {
  if (typeof raw !== 'object' || raw === null) return { books_finished: 0, endings_found: 0 }
  const t = raw as Partial<ProgressTotalsCard>
  return {
    books_finished: typeof t.books_finished === 'number' ? t.books_finished : 0,
    endings_found: typeof t.endings_found === 'number' ? t.endings_found : 0,
  }
}

export const EMPTY_PROGRESS: ProgressSummary = {
  badges: [],
  books: [],
  totals: { books_finished: 0, endings_found: 0 },
  days_read_this_week: 0,
  lifetime_days_read: 0,
  settings: FALLBACK_SETTINGS,
}

export interface ProgressReadOptions {
  /**
   * Issue a request of this caller's own instead of joining one already in
   * flight. For a caller whose read is ORDERED against a write rather than
   * simply wanting the current value.
   *
   * #CRITICAL: data integrity: the badge toast diffs a pre-completion badge
   * set against a post-completion read. Both halves must be requests of their
   * own: joining an in-flight mount-time read would compare against a snapshot
   * taken before the completion POST even existed, or (if that read never
   * settles, which a 10s axios timeout makes a real 10-second window) hang the
   * diff entirely and leave the G19 badges_enabled re-check unable to fire.
   * #VERIFY: ReaderPage.badgeToast.test.tsx "suppresses the toast when
   * badges_enabled is off, even if the mount-time settings fetch never
   * resolved"; progressApi.test.ts "a fresh read never joins one in flight".
   */
  fresh?: boolean
}

export interface ProgressApi {
  /** The caller's own progress (badges, collection state, totals, resolved
   * gamification settings). Child-token-scoped server-side; no profile id
   * parameter (mirrors `GET /v1/me`'s own "me" shape). */
  getProgress(options?: ProgressReadOptions): Promise<ProgressSummary>
}

/**
 * In-flight `GET /v1/me/progress` requests, keyed by the profile whose child
 * session issued them.
 *
 * Module-level rather than per-adapter on purpose: `useApi()` memoises on its
 * own `[config]`, so KidNav, LibraryPage and ReaderPage each hold a DIFFERENT
 * axios instance and each build their own adapter. A per-adapter map would
 * therefore dedupe nothing, which is the whole reason the same endpoint was
 * fetched two or three times on a single kid route.
 *
 * #CRITICAL: security: keyed by profile id, never global. `/v1/me/progress`
 * resolves from the child session token, so a global key would let a child who
 * switches readers mid-flight receive the PREVIOUS child's progress: the second
 * mount would join a request issued under a different session. Keying on the
 * profile makes that coalescing impossible rather than merely unlikely.
 * #VERIFY: progressApi.test.ts "never coalesces across profiles".
 */
const inFlightProgress = new Map<string, Promise<ProgressSummary>>()

/**
 * Drop every in-flight entry. Called from the global vitest setup so module
 * state cannot leak between test files.
 *
 * This exists because a request that NEVER settles never runs the `.finally`
 * that clears its key, and several suites deliberately mock exactly that (a
 * fetch left pending to assert an unmount guard). In the browser axios' 10s
 * timeout rejects such a request and the entry clears itself, so the wedge is
 * bounded there; in a test the module lives for the whole file and the wedge
 * is permanent, silently serving a later case a promise from an earlier one.
 */
export function clearInFlightProgress(): void {
  inFlightProgress.clear()
}

/**
 * @param profileId - The reading child, used only as the coalescing key (the
 *   request itself is "me"-scoped and carries no profile parameter). Omit to
 *   opt out of coalescing entirely, which is what a test wanting one request
 *   per call wants.
 */
export function makeProgressApi(api: AxiosInstance, profileId?: string): ProgressApi {
  const fetchProgress = async (): Promise<ProgressSummary> => {
    const res = await api.get<Partial<ProgressSummary>>('/v1/me/progress')
    const data = res.data
    // #ASSUME: data-integrity: a malformed/partial response (a stale mock,
    // a future contract change) degrades field-by-field to the empty/
    // fallback shape rather than throwing, so a shape mismatch on this
    // best-effort, decorative-only surface (ring, badge case, gallery)
    // never turns into a reader-blocking error. Every caller of this
    // adapter already treats a rejected promise the same permissive way,
    // but a malformed 200 would otherwise slip past that guard.
    // #VERIFY: progressApi.test.ts "tolerates a malformed response".
    return {
      badges: Array.isArray(data.badges) ? data.badges : [],
      books: Array.isArray(data.books) ? data.books : [],
      totals: normalizeTotals(data.totals),
      days_read_this_week:
        typeof data.days_read_this_week === 'number' ? data.days_read_this_week : 0,
      lifetime_days_read: typeof data.lifetime_days_read === 'number' ? data.lifetime_days_read : 0,
      settings: normalizeSettings(data.settings),
    }
  }
  return {
    getProgress(options?: ProgressReadOptions): Promise<ProgressSummary> {
      // A fresh read neither joins an in-flight entry nor becomes one: it must
      // not be handed someone else's older request, and a later mount must not
      // be handed this one either, since "fresh" is a property of the moment
      // this caller asked, not of the response.
      if (profileId === undefined || options?.fresh === true) return fetchProgress()
      const existing = inFlightProgress.get(profileId)
      if (existing !== undefined) return existing
      // #CRITICAL: concurrency: the entry is cleared INSIDE the promise the
      // caller receives, not in a separate `.then` on the raw fetch. That
      // ordering is what makes a sequential pair safe: every consumer
      // continuation runs on `started`, which settles only after the deletion
      // has already run, so a caller that awaits one result and then asks for
      // another can never be handed the first one back. ReaderPage's badge
      // toast depends on exactly that (it diffs a pre-completion snapshot
      // against a post-completion read; coalescing those two would compare a
      // value against itself and no badge would ever toast).
      // #VERIFY: progressApi.test.ts "a sequential second call is a fresh
      // request, not the settled first one".
      const started = fetchProgress().finally(() => {
        inFlightProgress.delete(profileId)
      })
      inFlightProgress.set(profileId, started)
      return started
    },
  }
}
