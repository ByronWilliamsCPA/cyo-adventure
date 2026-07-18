/**
 * Adapter from the axios instance to the guardian reading-visibility API (G9).
 *
 * Hand-typed request/response wiring, like the sibling adapters in this
 * directory (assignApi.ts, reviewApi.ts, intakeApi.ts): useApi()'s axios
 * instance carries the auth/refresh/correlation behavior every guardian call
 * needs, and none of that is wired into the generated sdk.gen.ts client. The
 * row shapes themselves are re-exported type-only from the generated
 * src/client/ (ChildEngagementItem, ReadingHistoryItem) so this adapter can
 * never silently drift from the committed OpenAPI contract.
 */

import type { AxiosInstance } from 'axios'

import type {
  ChildEngagementItem,
  FamilyReadingSummaryView,
  ReadingHistoryItem,
  ReadingHistoryView,
} from '../client'

export type { ChildEngagementItem, ReadingHistoryItem }

export interface ReadingApi {
  /** Per-child engagement signals for the caller's own family (G9). */
  familySummary(): Promise<ChildEngagementItem[]>
  /** One profile's per-storybook reading history (endings, progress). */
  history(profileId: string): Promise<ReadingHistoryItem[]>
}

export function makeReadingApi(api: AxiosInstance): ReadingApi {
  return {
    async familySummary(): Promise<ChildEngagementItem[]> {
      const res = await api.get<FamilyReadingSummaryView>(
        '/v1/families/me/reading-summary'
      )
      return res.data.children
    },
    async history(profileId: string): Promise<ReadingHistoryItem[]> {
      const res = await api.get<ReadingHistoryView>(
        `/v1/reading-history/${profileId}`
      )
      return res.data.books
    },
  }
}
