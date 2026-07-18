import type { AxiosInstance } from 'axios'

import type { ReadingHistoryItem, ReadingHistoryView } from '../client/types.gen'

/**
 * Hand-typed adapter for the library + ratings endpoints (repo convention:
 * mirror the backend Pydantic views by hand; the generated client is unused).
 * Backend contracts: src/cyo_adventure/api/schemas.py (LibraryItem,
 * LibraryProgress, RatingView).
 *
 * `history` (K6 endings tracker) is the one exception: its wire shape
 * (`ReadingHistoryItem`) is imported straight from the generated client
 * (`client/types.gen`) rather than hand-mirrored, matching childSessionApi.ts's
 * convention for a newer endpoint with no existing hand-typed precedent here.
 */

export type { ReadingHistoryItem } from '../client/types.gen'

export interface LibraryProgressView {
  current_node: string
  nodes_visited: number
  updated_at: string
  /**
   * True when the child reached an ending (shelf shows "Finished!", UX-K5).
   * Optional so a library list cached offline before this field existed still
   * types cleanly; a missing value reads as "not finished".
   */
  completed?: boolean
}

export interface LibraryItemView {
  id: string
  title: string
  version: number
  age_band: string
  tier: number
  reading_level_target: number
  node_count: number
  rating: number | null
  progress: LibraryProgressView | null
  series_id: string | null
  book_index: number | null
  cover_url: string | null
}

export interface RatingView {
  child_profile_id: string
  storybook_id: string
  value: number
  rated_at: string
  updated_at: string
}

export interface LibraryApi {
  list(profileId: string): Promise<LibraryItemView[]>
  rate(profileId: string, storybookId: string, value: number): Promise<RatingView>
  /** K6 endings tracker: one row per storybook the profile has any
   * completion for. Best-effort from the caller's point of view: a rejection
   * here must never block the shelf itself from rendering. */
  history(profileId: string): Promise<ReadingHistoryItem[]>
}

export function makeLibraryApi(api: AxiosInstance): LibraryApi {
  return {
    async list(profileId) {
      const res = await api.get<{ stories: LibraryItemView[] }>('/v1/library', {
        params: { profile_id: profileId },
      })
      return res.data.stories
    },
    async rate(profileId, storybookId, value) {
      const res = await api.post<RatingView>('/v1/ratings', {
        profile_id: profileId,
        storybook_id: storybookId,
        value,
      })
      return res.data
    },
    async history(profileId) {
      const res = await api.get<ReadingHistoryView>(`/v1/reading-history/${profileId}`)
      // #ASSUME: data-integrity: a well-formed response always has `books` as
      // an array (ReadingHistoryView). Defend against a malformed or
      // unexpectedly-shaped body anyway (this call shares the same GET
      // helper the rest of the page's mocked tests reuse for other
      // endpoints) so a bad payload degrades to "no badges" rather than
      // throwing out of a fire-and-forget .then() and going unhandled.
      // #VERIFY: LibraryPage.test.tsx K6 describe block.
      return Array.isArray(res.data.books) ? res.data.books : []
    },
  }
}
