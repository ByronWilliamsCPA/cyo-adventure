/**
 * Adapter for the kid story-request surface (Task 3.0). The kid UI runs under
 * the guardian token in R1; create posts the child's idea, listForProfile shows
 * the child their own request statuses. Moderation flags and other guardian-facing
 * fields are fetched over the wire in R1 but are explicitly stripped at this
 * adapter boundary to prevent accidental leakage into kid-surface code.
 */

import type { AxiosInstance } from 'axios'

export type StoryRequestStatus = 'pending' | 'approved' | 'declined' | 'blocked'

export interface KidStoryRequest {
  id: string
  status: StoryRequestStatus
  /** The guardian-confirmed series name (K12), when this request named one.
   * Null for a one-off idea or an anchor-driven "ask for the next book"
   * continuation. Used only as a best-effort hint for matching an approved
   * request to a book that has since appeared on the shelf; never shown
   * verbatim to the child. */
  proposedSeriesTitle: string | null
}

// Internal wire type: full response from backend (not exported)
interface WireStoryRequest {
  id: string
  status: StoryRequestStatus
  profile_id: string
  request_text: string
  created_at: string
  proposed_series_title?: string | null
  moderation_flags: Array<{
    category: string
    verdict: string
    message: string
  }>
}

export interface CreateStoryRequestExtras {
  proposedSeriesTitle?: string
  anchorStorybookId?: string
}

export interface KidStoryRequestApi {
  create(
    profileId: string,
    requestText: string,
    extras?: CreateStoryRequestExtras
  ): Promise<KidStoryRequest>
  listForProfile(profileId: string): Promise<KidStoryRequest[]>
}

export function makeKidStoryRequestApi(api: AxiosInstance): KidStoryRequestApi {
  return {
    async create(
      profileId: string,
      requestText: string,
      extras: CreateStoryRequestExtras = {}
    ): Promise<KidStoryRequest> {
      const res = await api.post<WireStoryRequest>('/v1/story-requests', {
        profile_id: profileId,
        request_text: requestText,
        ...(extras.proposedSeriesTitle !== undefined
          ? { proposed_series_title: extras.proposedSeriesTitle }
          : {}),
        ...(extras.anchorStorybookId !== undefined
          ? { anchor_storybook_id: extras.anchorStorybookId }
          : {}),
      })
      // Explicitly map to the kid-safe subset at runtime (same boundary as
      // listForProfile) so a guardian-facing field on the create response can
      // never leak into kid-surface code; a compile-time cast would not strip it.
      return {
        id: res.data.id,
        status: res.data.status,
        proposedSeriesTitle: res.data.proposed_series_title ?? null,
      }
    },
    async listForProfile(profileId: string): Promise<KidStoryRequest[]> {
      const res = await api.get<{ requests: WireStoryRequest[] }>(
        `/v1/story-requests?profile_id=${encodeURIComponent(profileId)}`
      )
      // Explicitly map to kid-safe subset to prevent guardian-facing fields from leaking
      return res.data.requests.map((r) => ({
        id: r.id,
        status: r.status,
        proposedSeriesTitle: r.proposed_series_title ?? null,
      }))
    },
  }
}
