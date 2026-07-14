/**
 * Adapter for the device-grant endpoints (ADR-014 Phase 3). Called from the
 * guardian console (ConsolePage's authorizeDevice()), so it always carries
 * the guardian's live Supabase bearer via the normal useApi() axios instance;
 * this module itself has no auth logic of its own.
 *
 * Wire-shape types come from the generated client (`client/types.gen`), the
 * single source of truth for this endpoint's request/response bodies, same
 * pattern as childSessionApi.ts.
 */

import type { AxiosInstance } from 'axios'

import type { DeviceGrantCreateBody, DeviceGrantListItem, DeviceGrantView } from '../client/types.gen'

export interface DeviceGrantApi {
  /**
   * Mint a device grant for the caller's own family (guardian/admin bearer
   * required). `label` is a free-text, guardian-facing device name
   * ("Kitchen tablet"); omitted when the guardian does not set one.
   */
  mint(label?: string): Promise<DeviceGrantView>
  /** List the family's non-revoked device grants. Never includes the token. */
  list(): Promise<DeviceGrantListItem[]>
  /** Revoke a device grant by id. */
  revoke(id: string): Promise<void>
}

export function makeDeviceGrantApi(api: AxiosInstance): DeviceGrantApi {
  return {
    async mint(label?: string): Promise<DeviceGrantView> {
      const body: DeviceGrantCreateBody | undefined = label === undefined ? undefined : { label }
      const res = await api.post<DeviceGrantView>('/v1/device-grants', body)
      return res.data
    },
    async list(): Promise<DeviceGrantListItem[]> {
      const res = await api.get<DeviceGrantListItem[]>('/v1/device-grants')
      return res.data
    },
    async revoke(id: string): Promise<void> {
      await api.delete(`/v1/device-grants/${id}`)
    },
  }
}
