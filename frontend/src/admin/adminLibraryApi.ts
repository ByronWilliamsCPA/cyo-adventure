// Hand-typed adapter like moderationDashboardApi.ts: the generated SDK in
// src/client/sdk.gen.ts is not used; axios calls inherit baseURL, auth,
// timeout, and 401 recovery from useApi()'s instance. Types come from the
// generated client so the OpenAPI drift gate keeps them honest.
import type { AxiosInstance } from 'axios'

import type { StorybookLibraryView, StorybookSummary } from '../client/types.gen'

export type { StorybookSummary }

const BASE_PATH = '/v1/admin/storybooks'

export interface AdminLibraryApi {
  /** List every storybook (P19), optionally filtered to one lifecycle status. */
  list(status?: string): Promise<StorybookSummary[]>
}

export function makeAdminLibraryApi(api: AxiosInstance): AdminLibraryApi {
  return {
    async list(status?: string): Promise<StorybookSummary[]> {
      const res = await api.get<StorybookLibraryView>(BASE_PATH, {
        params: status ? { status } : undefined,
      })
      return res.data.items
    },
  }
}
