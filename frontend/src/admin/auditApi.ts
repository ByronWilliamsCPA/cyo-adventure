/**
 * Adapter from the axios instance to the admin audit log API (register A13,
 * the view half; M5 / Phase 5 deliverable: `GET /v1/admin/audit`, a
 * filterable read surface over the append-only pipeline_event log).
 *
 * Hand-typed like moderationDashboardApi.ts and moderationThresholdsApi.ts,
 * but every type here is defined locally rather than imported from
 * '../client/types.gen': this backend route is brand new and the generated
 * client has not been regenerated against it yet (the supervisor regenerates
 * src/client/ once the backend PR lands; see the module docstring of
 * api/audit.py for the wire contract this mirrors). Calls go through
 * useApi()'s axios instance so this adapter inherits the same
 * baseURL/auth/401-recovery every other admin page gets.
 */
import type { AxiosInstance } from 'axios'

const BASE_PATH = '/v1/admin/audit'

/**
 * One append-only pipeline_event row, projected for the admin console.
 * Mirrors `cyo_adventure.api.audit.AuditEventView`.
 */
export interface AuditEventView {
  id: string
  occurred_at: string
  actor_id: string | null
  actor_role: string
  entity_type: string
  entity_id: string
  event_type: string
  from_state: string | null
  to_state: string | null
  payload: Record<string, unknown>
}

/** A page of the audit log, newest first. Mirrors `AuditListView`. */
export interface AuditListView {
  events: AuditEventView[]
  limit: number
  offset: number
  has_more: boolean
}

/**
 * Query filters for `list()`. Every field is optional and composes with AND,
 * mirroring `cyo_adventure.api.audit.AuditFilters`. Timestamps are raw
 * ISO-8601 strings (a bare `YYYY-MM-DD` date is accepted by the backend's
 * `datetime.fromisoformat`), passed through unmodified rather than converted
 * client-side, so this adapter carries no timezone-conversion logic of its
 * own.
 */
export interface ListAuditEventsParams {
  kind?: string
  actorId?: string
  storybookId?: string
  profileId?: string
  since?: string
  until?: string
  limit?: number
  offset?: number
}

export interface AuditApi {
  list(params?: ListAuditEventsParams): Promise<AuditListView>
}

export function makeAuditApi(api: AxiosInstance): AuditApi {
  return {
    async list(params?: ListAuditEventsParams): Promise<AuditListView> {
      const res = await api.get<AuditListView>(BASE_PATH, {
        params: {
          kind: params?.kind,
          actor_id: params?.actorId,
          storybook_id: params?.storybookId,
          profile_id: params?.profileId,
          since: params?.since,
          until: params?.until,
          limit: params?.limit,
          offset: params?.offset,
        },
      })
      return res.data
    },
  }
}
