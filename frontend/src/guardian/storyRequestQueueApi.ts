/**
 * Adapter for the guardian/admin story-request review queue (Task 3.0).
 *
 * Hand-typed like assignApi.ts: the generated client is not committed. Types
 * mirror StoryRequestView / StoryRequestListView in api/schemas.py.
 */

import type { AxiosInstance } from 'axios'

import type { FindingVerdict } from './reviewApi'

export type StoryRequestStatus = 'pending' | 'approved' | 'declined' | 'blocked'

export interface StoryRequestFlag {
  category: string
  verdict: FindingVerdict
  message: string
}

export interface StoryRequestView {
  id: string
  profile_id: string
  status: StoryRequestStatus
  request_text: string | null
  moderation_flags: StoryRequestFlag[]
  created_at: string
}

export interface StoryRequestApproved {
  id: string
  status: 'approved'
  concept_id: string
  job_id: string
}

export interface StoryRequestDeclined {
  id: string
  status: 'declined'
}

export interface StoryRequestQueueApi {
  listPending(): Promise<StoryRequestView[]>
  approve(id: string): Promise<StoryRequestApproved>
  decline(id: string): Promise<StoryRequestDeclined>
}

export function makeStoryRequestQueueApi(api: AxiosInstance): StoryRequestQueueApi {
  return {
    async listPending(): Promise<StoryRequestView[]> {
      const res = await api.get<{ requests: StoryRequestView[] }>(
        '/v1/story-requests?status=pending'
      )
      return res.data.requests
    },
    async approve(id: string): Promise<StoryRequestApproved> {
      const res = await api.post<StoryRequestApproved>(
        `/v1/story-requests/${id}/approve`
      )
      return res.data
    },
    async decline(id: string): Promise<StoryRequestDeclined> {
      const res = await api.post<StoryRequestDeclined>(
        `/v1/story-requests/${id}/decline`
      )
      return res.data
    },
  }
}
