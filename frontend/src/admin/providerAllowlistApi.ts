/**
 * Adapter for the admin provider-allowlist API (src/cyo_adventure/api/
 * provider_allowlist.py). Hand-typed like moderationThresholdsApi.ts: calls
 * go directly on `useApi()`'s axios instance rather than through the
 * generated SDK, so this inherits baseURL/auth/timeout/401-recovery; only
 * the generated *types* are reused.
 *
 * This is a global, cost-control settings surface (which (provider, model_id)
 * pairs the generation pipeline is permitted to call at all), independent of
 * any single story; it is a validation gate the authoring-plan step checks
 * against, not a per-story picker (see authoringPlanApi.ts for that).
 */

import { type AxiosInstance } from 'axios'

import type {
  AllowlistCreateBody,
  AllowlistListView,
  AllowlistUpdateBody,
  AllowlistView,
} from '../client/types.gen'

const BASE_PATH = '/v1/admin/provider-allowlist'

export interface ProviderAllowlistApi {
  list(): Promise<AllowlistListView>
  create(body: AllowlistCreateBody): Promise<AllowlistView>
  update(id: string, body: AllowlistUpdateBody): Promise<AllowlistView>
  remove(id: string): Promise<AllowlistListView>
}

export function makeProviderAllowlistApi(api: AxiosInstance): ProviderAllowlistApi {
  return {
    async list(): Promise<AllowlistListView> {
      const res = await api.get<AllowlistListView>(BASE_PATH)
      return res.data
    },
    async create(body: AllowlistCreateBody): Promise<AllowlistView> {
      const res = await api.post<AllowlistView>(BASE_PATH, body)
      return res.data
    },
    async update(id: string, body: AllowlistUpdateBody): Promise<AllowlistView> {
      const res = await api.put<AllowlistView>(`${BASE_PATH}/${id}`, body)
      return res.data
    },
    // The delete endpoint returns the full refreshed list view, so no
    // separate list() round-trip is needed after a successful removal
    // (mirrors moderationThresholdsApi.ts's remove()).
    async remove(id: string): Promise<AllowlistListView> {
      const res = await api.delete<AllowlistListView>(`${BASE_PATH}/${id}`)
      return res.data
    },
  }
}
