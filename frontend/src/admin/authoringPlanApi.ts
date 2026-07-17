/**
 * Adapter for the admin authoring-plan step (src/cyo_adventure/api/
 * story_requests.py, GET /admin/story-requests?status=approved and POST
 * /story-requests/{id}/authoring-plan). Hand-typed like
 * moderationThresholdsApi.ts/providerAllowlistApi.ts: calls go directly on
 * `useApi()`'s axios instance, only the generated *types* are reused.
 *
 * This is the step between a guardian/admin approving a story REQUEST
 * (StoryRequestQueue, which already sets age_band/length/narrative_style)
 * and generation actually starting: an admin picks the authoring
 * method/mechanism and, for an automated provider, the specific
 * provider/model, validated against the provider allowlist
 * (providerAllowlistApi.ts) server-side.
 */

import { type AxiosInstance } from 'axios'

import type { AuthoringPlanRequest, AuthoringPlanResponse } from '../client/types.gen'
import type { StoryRequestView } from '../guardian/storyRequestQueueApi'

const REQUESTS_PATH = '/v1/admin/story-requests'

export interface AuthoringPlanApi {
  listApproved(): Promise<StoryRequestView[]>
  createPlan(requestId: string, body: AuthoringPlanRequest): Promise<AuthoringPlanResponse>
}

export function makeAuthoringPlanApi(api: AxiosInstance): AuthoringPlanApi {
  return {
    async listApproved(): Promise<StoryRequestView[]> {
      const res = await api.get<{ requests: StoryRequestView[] }>(
        `${REQUESTS_PATH}?status=approved`
      )
      return res.data.requests
    },
    async createPlan(
      requestId: string,
      body: AuthoringPlanRequest
    ): Promise<AuthoringPlanResponse> {
      const res = await api.post<AuthoringPlanResponse>(
        `/v1/story-requests/${requestId}/authoring-plan`,
        body
      )
      return res.data
    },
  }
}
