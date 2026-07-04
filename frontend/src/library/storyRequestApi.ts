/**
 * Adapter for the kid story-request surface (Task 3.0). The kid UI runs under
 * the guardian token in R1; create posts the child's idea, listForProfile shows
 * the child their own request statuses. Moderation flags are never fetched or
 * rendered on the kid surface.
 */

import type { AxiosInstance } from 'axios'

export type StoryRequestStatus = 'pending' | 'approved' | 'declined' | 'blocked'

export interface KidStoryRequest {
  id: string
  status: StoryRequestStatus
}

export interface KidStoryRequestApi {
  create(profileId: string, requestText: string): Promise<KidStoryRequest>
  listForProfile(profileId: string): Promise<KidStoryRequest[]>
}

export function makeKidStoryRequestApi(api: AxiosInstance): KidStoryRequestApi {
  return {
    async create(profileId: string, requestText: string): Promise<KidStoryRequest> {
      const res = await api.post<{ id: string; status: StoryRequestStatus }>(
        '/v1/story-requests',
        { profile_id: profileId, request_text: requestText }
      )
      return res.data
    },
    async listForProfile(profileId: string): Promise<KidStoryRequest[]> {
      const res = await api.get<{ requests: KidStoryRequest[] }>(
        `/v1/story-requests?profile_id=${profileId}`
      )
      return res.data.requests
    },
  }
}
