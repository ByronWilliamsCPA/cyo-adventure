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

import type {
  NoiseFloorUpdateBody,
  NoiseFloorView,
  ThresholdListView,
  ThresholdUpsertBody,
  ThresholdView,
} from '../client/types.gen'

const BASE_PATH = '/v1/admin/moderation-thresholds'
const NOISE_FLOOR_PATH = '/v1/admin/moderation/noise-floor'

export interface ThresholdsApi {
  list(): Promise<ThresholdListView>
  upsert(ageBand: string, category: string, body: ThresholdUpsertBody): Promise<ThresholdView>
  remove(ageBand: string, category: string): Promise<ThresholdListView>
  getNoiseFloor(): Promise<NoiseFloorView>
  setNoiseFloor(value: number): Promise<NoiseFloorView>
}

export function makeThresholdsApi(api: AxiosInstance): ThresholdsApi {
  return {
    async list(): Promise<ThresholdListView> {
      const res = await api.get<ThresholdListView>(BASE_PATH)
      return res.data
    },
    // `category` travels as a QUERY parameter, never a path segment: five
    // known categories contain '/' (e.g. self-harm/instructions), and a
    // slash in a path segment breaks backend route matching and 404s.
    async upsert(
      ageBand: string,
      category: string,
      body: ThresholdUpsertBody
    ): Promise<ThresholdView> {
      const res = await api.put<ThresholdView>(`${BASE_PATH}/${ageBand}`, body, {
        params: { category },
      })
      return res.data
    },
    // The delete endpoint returns the full refreshed list view, so no
    // separate list() round-trip is needed after a successful removal.
    async remove(ageBand: string, category: string): Promise<ThresholdListView> {
      const res = await api.delete<ThresholdListView>(`${BASE_PATH}/${ageBand}`, {
        params: { category },
      })
      return res.data
    },
    // Admin noise floor (WS-A admin noise-floor addendum, Task A4): the
    // global ADVISORY-score cutoff that denoises the admin review surface.
    async getNoiseFloor(): Promise<NoiseFloorView> {
      const res = await api.get<NoiseFloorView>(NOISE_FLOOR_PATH)
      return res.data
    },
    async setNoiseFloor(value: number): Promise<NoiseFloorView> {
      const body: NoiseFloorUpdateBody = { value }
      const res = await api.put<NoiseFloorView>(NOISE_FLOOR_PATH, body)
      return res.data
    },
  }
}
