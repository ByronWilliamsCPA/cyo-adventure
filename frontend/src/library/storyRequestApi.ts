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
  /** The child's own idea text, so pending rows are distinguishable (UX-K3). */
  request_text: string
  /** The guardian-confirmed series name (K12), when this request named one.
   * Null for a one-off idea or an anchor-driven "ask for the next book"
   * continuation. */
  proposedSeriesTitle: string | null
  /** W0.4: the storybook this request produced, once the backend has
   * stamped it (publishing/service.py::approve(), at publish time). Null
   * until then. A non-null value here always names a published book (see
   * the backend's #ASSUME on api/story_requests.py::_to_view), but it may
   * not yet be assigned to this child's shelf; RequestStory only flips its
   * "it's on your shelf!" copy once this id also appears in the profile's
   * own library list. */
  resultingStorybookId: string | null
  /**
   * W1.4 (K19 reflect-back, design review 4.1): the request view's
   * ``interpretation.kid_summary`` field only -- a single pre-rendered,
   * template-authored, echo-safe sentence
   * (``story_requests/interpretation.py::_kid_summary``), e.g. "We built in
   * 1 of your ideas.". Deliberately NOT the per-element
   * ``interpretation.elements[].kid_text``/``element`` list, and NEVER
   * ``interpretation.guardian_summary`` or any element's ``guardian_text``:
   * this adapter's whole job is stripping guardian-facing fields at the
   * wire boundary (see the module docstring), and the summary is the one
   * field the backend already designed to stand alone as a short,
   * kid-appropriate reflection of the whole request -- picking the raw
   * element list instead would mean choosing which of possibly several
   * requested elements to show and in what order, a UI judgment call the
   * per-request summary already makes once, server-side, for every band.
   * Null for a request created before WS-7 shipped (no stored
   * interpretation) or when the backend omits the field entirely.
   */
  kidSummary: string | null
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
  resulting_storybook_id?: string | null
  // Only the one field this adapter reads is declared; guardian_summary and
  // the elements[] list (each carrying a guardian_text field) exist on the
  // real wire payload but are never referenced here, so they can never leak
  // into kid-surface code even by accident (see kidSummary's own doc above).
  interpretation?: { kid_summary: string } | null
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
        request_text: res.data.request_text,
        proposedSeriesTitle: res.data.proposed_series_title ?? null,
        resultingStorybookId: res.data.resulting_storybook_id ?? null,
        kidSummary: res.data.interpretation?.kid_summary ?? null,
      }
    },
    async listForProfile(profileId: string): Promise<KidStoryRequest[]> {
      const res = await api.get<{ requests: WireStoryRequest[] }>(
        `/v1/story-requests?profile_id=${encodeURIComponent(profileId)}`
      )
      // Explicitly map to kid-safe subset to prevent guardian-facing fields
      // from leaking. request_text is the child's OWN idea (not guardian-facing)
      // and is surfaced so pending rows are distinguishable (UX-K3).
      return res.data.requests.map((r) => ({
        id: r.id,
        status: r.status,
        request_text: r.request_text,
        proposedSeriesTitle: r.proposed_series_title ?? null,
        resultingStorybookId: r.resulting_storybook_id ?? null,
        kidSummary: r.interpretation?.kid_summary ?? null,
      }))
    },
  }
}
