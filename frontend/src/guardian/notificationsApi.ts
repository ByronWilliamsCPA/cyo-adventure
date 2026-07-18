/**
 * Adapter from the axios instance to the guardian notification feed (G10).
 *
 * Hand-typed like readingApi.ts and the other adapters in this directory:
 * useApi()'s axios instance carries the auth/refresh/correlation behavior
 * this call needs, and none of that is wired into the generated
 * sdk.gen.ts client. NotificationView is re-exported type-only from the
 * generated src/client/ so this adapter cannot silently drift from the
 * committed OpenAPI contract.
 */

import type { AxiosInstance } from 'axios'

import type { NotificationListView, NotificationView } from '../client'

export type { NotificationView }

export interface ListNotificationsParams {
  /**
   * ISO-8601 lower bound (exclusive) on occurred_at. Omit to fetch with no
   * lower bound (the backend's default page, newest first).
   */
  since?: string
  /** Max items to return; the backend defaults to 30, clamped to [1, 100]. */
  limit?: number
}

export interface NotificationsApi {
  list(params?: ListNotificationsParams): Promise<NotificationView[]>
}

export function makeNotificationsApi(api: AxiosInstance): NotificationsApi {
  return {
    async list(params?: ListNotificationsParams): Promise<NotificationView[]> {
      const res = await api.get<NotificationListView>('/v1/notifications', {
        params: {
          since: params?.since,
          limit: params?.limit,
        },
      })
      // #ASSUME: data-integrity: the backend always returns a `notifications`
      // array (NotificationListView.notifications has no default and is
      // never omitted by the route handler), but this degrades to [] rather
      // than throwing on an unexpected/malformed body, matching the
      // defensive-read convention elsewhere in these adapters (e.g.
      // reviewApi.ts's stillProcessing()).
      // #VERIFY: notificationsApi.test.ts "malformed body degrades to []".
      return res.data.notifications ?? []
    },
  }
}
