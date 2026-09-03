// Hand-typed adapter like moderationDashboardApi.ts: the generated SDK in
// src/client/sdk.gen.ts is not used; axios calls inherit baseURL, auth,
// timeout, and 401 recovery from useApi()'s instance. Types come from the
// generated client so the OpenAPI drift gate keeps them honest.
import type { AxiosInstance } from 'axios'

import type {
  OutstandingDecisionItem,
  OutstandingDecisionsView,
  RecalledView,
  RecallRequest,
} from '../client/types.gen'

export type { OutstandingDecisionItem }
export type RecallReasonCode = RecallRequest['reason_code']

export interface OutstandingDecisionsApi {
  list(): Promise<OutstandingDecisionItem[]>
  recall(storybookId: string, reasonCode: RecallReasonCode): Promise<RecalledView>
}

export function makeOutstandingDecisionsApi(api: AxiosInstance): OutstandingDecisionsApi {
  return {
    async list(): Promise<OutstandingDecisionItem[]> {
      const res = await api.get<OutstandingDecisionsView>('/v1/admin/outstanding-decisions')
      return res.data.items
    },
    async recall(storybookId: string, reasonCode: RecallReasonCode): Promise<RecalledView> {
      const res = await api.post<RecalledView>(`/v1/storybooks/${storybookId}/recall`, {
        reason_code: reasonCode,
      })
      return res.data
    },
  }
}
