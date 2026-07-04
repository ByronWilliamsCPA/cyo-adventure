/**
 * Adapter from the axios instance to the assignment API (C4a-6).
 *
 * Hand-typed like profilesApi.ts: the generated client is not committed and
 * nothing imports it. Types mirror AssignmentListView in
 * src/cyo_adventure/api/schemas.py.
 */

import type { AxiosInstance } from 'axios'

import type { FindingVerdict, ReviewSummary } from './reviewApi'

export interface AssignmentList {
  storybook_id: string
  profile_ids: string[]
}

export interface ContentFinding {
  category: string
  verdict: FindingVerdict
  message: string
}

export interface ContentSummary {
  storybook_id: string
  version: number
  screened: boolean
  summary: ReviewSummary | null
  flagged_count: number
  findings: ContentFinding[]
}

export interface GuardianBookItem {
  storybook_id: string
  title: string
  version: number
  age_band: string
  screened: boolean
  flagged_count: number
  assigned_profile_ids: string[]
}

export interface GuardianBooksView {
  books: GuardianBookItem[]
}

export interface AssignApi {
  get(storybookId: string): Promise<string[]>
  add(storybookId: string, profileIds: string[]): Promise<string[]>
  contentSummary(storybookId: string): Promise<ContentSummary>
  listBooks(): Promise<GuardianBookItem[]>
}

export function makeAssignApi(api: AxiosInstance): AssignApi {
  return {
    async get(storybookId: string): Promise<string[]> {
      const res = await api.get<AssignmentList>(
        `/v1/storybooks/${storybookId}/assignments`
      )
      return res.data.profile_ids
    },
    async add(storybookId: string, profileIds: string[]): Promise<string[]> {
      const res = await api.post<AssignmentList>(
        `/v1/storybooks/${storybookId}/assignments`,
        { profile_ids: profileIds }
      )
      return res.data.profile_ids
    },
    async contentSummary(storybookId: string): Promise<ContentSummary> {
      const res = await api.get<ContentSummary>(
        `/v1/storybooks/${storybookId}/content-summary`
      )
      return res.data
    },
    async listBooks(): Promise<GuardianBookItem[]> {
      const res = await api.get<GuardianBooksView>('/v1/guardian/books')
      return res.data.books
    },
  }
}
