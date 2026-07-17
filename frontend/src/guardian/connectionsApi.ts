/**
 * Adapter from the axios instance to the guardian family-connection consent
 * API (ADR-016, register G17).
 *
 * Hand-typed like the sibling adapters in this directory (readingApi.ts,
 * notificationsApi.ts, storyRequestQueueApi.ts): useApi()'s axios instance
 * carries the auth/refresh/correlation behavior this call needs, and none of
 * that is wired into the generated sdk.gen.ts client. Unlike readingApi.ts's
 * types (which already exist in the generated client from an earlier
 * commit), the shapes below are new for this change and are being added to
 * the backend in the same change set, not yet in src/client/ -- they are
 * defined locally here rather than re-exported, and will fold into the
 * generated client the next time it is regenerated.
 *
 * ADR-016: a connection carries a book pointer, a rating, and a display
 * name, never free text; this adapter's own surface (consent state, family
 * names) mirrors that same structured-data-only posture.
 */

import type { AxiosInstance } from 'axios'

/** Relative to the caller's own family: which side of the directional
 * connection it sits on. "viewer" means the caller's family would see the
 * counterpart's recommendations; "sharer" means the counterpart would see
 * the caller's. */
export type ConnectionDirection = 'viewer' | 'sharer'

export interface FamilyConnectionMineItem {
  id: string
  direction: ConnectionDirection
  counterpart_family_id: string
  counterpart_family_name: string
  /** Whether the caller's OWN family has consented on their side. */
  my_consent: boolean
  /** Whether BOTH sides have consented (ADR-016 dual-guardian rule); only
   * then does anything actually flow. */
  active: boolean
  created_at: string
}

export interface ConnectionsApi {
  /** Every connection touching the caller's family, from their own side. */
  listMine(): Promise<FamilyConnectionMineItem[]>
  /** Record the caller's guardian consent for their side of a connection. */
  consent(connectionId: string): Promise<FamilyConnectionMineItem>
  /** Revoke the caller's guardian consent for their side of a connection. */
  revoke(connectionId: string): Promise<FamilyConnectionMineItem>
}

export function makeConnectionsApi(api: AxiosInstance): ConnectionsApi {
  return {
    async listMine(): Promise<FamilyConnectionMineItem[]> {
      const res = await api.get<{ connections: FamilyConnectionMineItem[] }>(
        '/v1/family-connections/mine'
      )
      // #ASSUME: data integrity: the backend always returns a `connections`
      // array, but this degrades to [] on a malformed body rather than
      // throwing, matching the defensive-read convention elsewhere in these
      // adapters (e.g. notificationsApi.ts's list()).
      // #VERIFY: connectionsApi.test.ts "malformed body degrades to []".
      return Array.isArray(res.data.connections) ? res.data.connections : []
    },
    async consent(connectionId: string): Promise<FamilyConnectionMineItem> {
      const res = await api.post<FamilyConnectionMineItem>(
        `/v1/family-connections/${connectionId}/consent`
      )
      return res.data
    },
    async revoke(connectionId: string): Promise<FamilyConnectionMineItem> {
      const res = await api.delete<FamilyConnectionMineItem>(
        `/v1/family-connections/${connectionId}/consent`
      )
      return res.data
    },
  }
}
