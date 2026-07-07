/**
 * Adapter from the axios instance to the admin moderation-thresholds API
 * (WS-A Task 7). Hand-typed like reviewApi.ts and readerApi.ts: the endpoints
 * are called directly on `useApi()`'s axios instance rather than through the
 * generated SDK (`src/client/sdk.gen.ts`), so this page inherits the same
 * baseURL, Authorization header, timeout, and 401 recovery every other
 * guardian page gets from `useApi()`. Only the generated *types* (the actual
 * source of truth for the wire shapes) are reused.
 */

import { type AxiosInstance } from 'axios'

import type { ThresholdListView, ThresholdUpsertBody, ThresholdView } from '../client/types.gen'

const BASE_PATH = '/v1/admin/moderation-thresholds'

export interface ThresholdsApi {
  list(): Promise<ThresholdListView>
  upsert(ageBand: string, category: string, body: ThresholdUpsertBody): Promise<ThresholdView>
  remove(ageBand: string, category: string): Promise<ThresholdListView>
}

export function makeThresholdsApi(api: AxiosInstance): ThresholdsApi {
  return {
    async list(): Promise<ThresholdListView> {
      const res = await api.get<ThresholdListView>(BASE_PATH)
      return res.data
    },
    async upsert(
      ageBand: string,
      category: string,
      body: ThresholdUpsertBody
    ): Promise<ThresholdView> {
      const res = await api.put<ThresholdView>(
        `${BASE_PATH}/${ageBand}/${category}`,
        body
      )
      return res.data
    },
    // The delete endpoint returns the full refreshed list view, so no
    // separate list() round-trip is needed after a successful removal.
    async remove(ageBand: string, category: string): Promise<ThresholdListView> {
      const res = await api.delete<ThresholdListView>(`${BASE_PATH}/${ageBand}/${category}`)
      return res.data
    },
  }
}
