// Hand-typed adapter like moderationThresholdsApi.ts: the generated SDK in
// src/client/sdk.gen.ts is not used; axios calls inherit baseURL, auth,
// timeout, and 401 recovery from useApi()'s instance. Types come from the
// generated client so the OpenAPI drift gate keeps them honest.
import type { AxiosInstance } from 'axios'

import type { ModerationDashboardView, SuggestionListView } from '../client/types.gen'

const BASE_PATH = '/v1/admin/moderation'

export interface ModerationDashboardApi {
  dashboard(): Promise<ModerationDashboardView>
  suggestions(): Promise<SuggestionListView>
}

export function makeModerationDashboardApi(api: AxiosInstance): ModerationDashboardApi {
  return {
    async dashboard(): Promise<ModerationDashboardView> {
      const res = await api.get<ModerationDashboardView>(`${BASE_PATH}/dashboard`)
      return res.data
    },
    async suggestions(): Promise<SuggestionListView> {
      const res = await api.get<SuggestionListView>(`${BASE_PATH}/suggestions`)
      return res.data
    },
  }
}
