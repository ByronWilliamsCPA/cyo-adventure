/**
 * Adapter for minting a child session (G1 / P6-04). Hand-typed like
 * authoredRequestApi.ts: called directly on `useApi()`'s axios instance
 * rather than through the generated SDK function, but the wire-shape types
 * come from the generated client (`client/types.gen`), the single source of
 * truth for this endpoint's request/response bodies.
 */

import type { AxiosInstance } from 'axios'

import type { ChildSessionCreateBody, ChildSessionView } from '../client/types.gen'

export interface ChildSessionApi {
  /**
   * Mint a child session token for one profile (guardian/admin bearer
   * required). `pin` is the profile's picker PIN (P6-07); pass it only when
   * the profile has one, and never persist it anywhere.
   */
  mint(profileId: string, pin?: string): Promise<ChildSessionView>
}

export function makeChildSessionApi(api: AxiosInstance): ChildSessionApi {
  return {
    async mint(profileId: string, pin?: string): Promise<ChildSessionView> {
      const body: ChildSessionCreateBody =
        pin === undefined
          ? { profile_id: profileId }
          : { profile_id: profileId, pin }
      const res = await api.post<ChildSessionView>('/v1/child-sessions', body)
      return res.data
    },
  }
}
