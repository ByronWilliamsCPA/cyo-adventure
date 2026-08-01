/**
 * Adapter for `GET /v1/me/progress` (W3.1/W3.2/W3.4).
 *
 * Hand-typed like `storyStatusApi.ts`'s own wire-shape comment: this route's
 * response gained `found_endings`, `days_read_this_week`,
 * `lifetime_days_read`, and `settings` fields (W3.2/W3.4, this change) after
 * the last client regeneration, so `src/client/types.gen.ts`'s `ProgressView`
 * is stale relative to the live backend response. Regenerate
 * (`npm run generate-client`, backend running) once this change lands, then
 * this file's request/response types can be swapped for the generated ones;
 * the wire shape should already match.
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

// #ASSUME: data integrity: unlike the backend's own inert fallback (which
// resolves a genuinely missing profile row to the P-A "on" default, since it
// must always answer with SOME concrete value), a CLIENT-SIDE fetch failure
// means this device simply does not know the real resolved settings yet.
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

export const EMPTY_PROGRESS: ProgressSummary = {
  badges: [],
  books: [],
  totals: { books_finished: 0, endings_found: 0 },
  days_read_this_week: 0,
  lifetime_days_read: 0,
  settings: FALLBACK_SETTINGS,
}

export interface ProgressApi {
  /** The caller's own progress (badges, collection state, totals, resolved
   * gamification settings). Child-token-scoped server-side; no profile id
   * parameter (mirrors `GET /v1/me`'s own "me" shape). */
  getProgress(): Promise<ProgressSummary>
}

export function makeProgressApi(api: AxiosInstance): ProgressApi {
  return {
    async getProgress(): Promise<ProgressSummary> {
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
        totals: data.totals ?? EMPTY_PROGRESS.totals,
        days_read_this_week:
          typeof data.days_read_this_week === 'number' ? data.days_read_this_week : 0,
        lifetime_days_read:
          typeof data.lifetime_days_read === 'number' ? data.lifetime_days_read : 0,
        settings: data.settings ?? FALLBACK_SETTINGS,
      }
    },
  }
}
