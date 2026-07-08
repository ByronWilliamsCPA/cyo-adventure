/**
 * Adapter for the guardian/admin "authored" story-request form (WS-B PR 2): a
 * pre-approved request that skips the child story-request moderation queue.
 * Hand-typed like moderationThresholdsApi.ts: the endpoints are called
 * directly on `useApi()`'s axios instance rather than through the generated
 * SDK, but the wire-shape types come from the generated client
 * (`client/types.gen`), which is the source of truth for this endpoint.
 */

import type { AxiosInstance } from 'axios'

import type {
  FamilyView,
  ProfileView,
  StoryRequestAuthoredCreateBody,
  StoryRequestAuthoredCreatedView,
} from '../client/types.gen'

export interface AuthoredRequestApi {
  createAuthored(body: StoryRequestAuthoredCreateBody): Promise<StoryRequestAuthoredCreatedView>
  listProfiles(): Promise<ProfileView[]>
  listFamilies(): Promise<FamilyView[]>
}

export function makeAuthoredRequestApi(api: AxiosInstance): AuthoredRequestApi {
  return {
    async createAuthored(
      body: StoryRequestAuthoredCreateBody
    ): Promise<StoryRequestAuthoredCreatedView> {
      const res = await api.post<StoryRequestAuthoredCreatedView>(
        '/v1/story-requests/authored',
        body
      )
      return res.data
    },
    async listProfiles(): Promise<ProfileView[]> {
      const res = await api.get<{ profiles: ProfileView[] }>('/v1/profiles')
      return res.data.profiles
    },
    async listFamilies(): Promise<FamilyView[]> {
      const res = await api.get<{ families: FamilyView[] }>('/v1/admin/families')
      return res.data.families
    },
  }
}
