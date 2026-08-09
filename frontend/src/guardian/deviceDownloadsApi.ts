/**
 * Adapter for the G15 storage/download view endpoints (backend:
 * api/offline_downloads.py). Called from the guardian console, so it always
 * carries the guardian's live Supabase bearer via the normal useApi() axios
 * instance, mirroring auth/deviceGrantApi.ts.
 *
 * Wire-shape types come from the generated client (`client/types.gen`), the
 * single source of truth for this endpoint's response body.
 */

import type { AxiosInstance } from 'axios'

import type { DeviceDownloadView } from '../client/types.gen'

export interface DeviceDownloadsApi {
  /** List the family's offline-download inventory, newest-confirmed first. */
  list(): Promise<DeviceDownloadView[]>
}

export function makeDeviceDownloadsApi(api: AxiosInstance): DeviceDownloadsApi {
  return {
    async list(): Promise<DeviceDownloadView[]> {
      const res = await api.get<DeviceDownloadView[]>('/v1/device-downloads')
      return res.data
    },
  }
}
