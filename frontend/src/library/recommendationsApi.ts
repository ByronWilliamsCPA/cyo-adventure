import type { AxiosInstance } from 'axios'

/**
 * Hand-typed adapter for the K17 recommendations feed (ADR-016 rings 1-2:
 * within the family, and guardian-connected families, the cousins case).
 * Repo convention: mirror the backend Pydantic view by hand rather than
 * depend on the generated client (see libraryApi.ts's header note); this
 * endpoint is also being built concurrently by a sibling backend PR, so
 * regenerating against it is out of scope for this change.
 *
 * Backend contract (fixed, coordinated out of band with the sibling PR):
 * GET /v1/recommendations/{profile_id} -> { items: RecommendationItem[] }.
 *
 * #ASSUME: external resources: the backend endpoint is being built
 * concurrently and may not exist yet, may 404, or may shift shape before it
 * lands.
 * #VERIFY: every caller of `list` treats a rejection as best-effort (no
 * chips), never a page-level error; see LibraryPage's recommendations fetch
 * and this adapter's own tests below.
 *
 * ADR-016: a recommendation is structured data only, book pointer, rating,
 * and a recommender display name, never a message. This type MUST NOT grow a
 * free-text field (no note, no reply, no body).
 */

export type RecommendationRing = 'family' | 'connection'

export interface RecommendationItem {
  storybook_id: string
  title: string
  cover_url: string | null
  recommender_name: string
  rating: number
  ring: RecommendationRing
}

export interface RecommendationsApi {
  /** Best-effort from the caller's point of view: a rejection here must
   * never block or error the shelf; the caller should degrade to "no chips"
   * on any failure (ADR-016 design point 3, kid-safe by default). */
  list(profileId: string): Promise<RecommendationItem[]>
}

export function makeRecommendationsApi(api: AxiosInstance): RecommendationsApi {
  return {
    async list(profileId) {
      const res = await api.get<{ items: RecommendationItem[] }>(
        `/v1/recommendations/${profileId}`
      )
      // #ASSUME: data integrity: a well-formed response always has `items`
      // as an array. Defend against a malformed or unexpectedly-shaped body
      // anyway, so a bad payload degrades to "no chips" rather than throwing
      // out of a fire-and-forget caller.
      // #VERIFY: recommendationsApi.test.ts and LibraryPage.test.tsx K17
      // describe block.
      return Array.isArray(res.data.items) ? res.data.items : []
    },
  }
}
