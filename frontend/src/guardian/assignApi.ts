/**
 * Adapter from the axios instance to the assignment API (C4a-6).
 *
 * Hand-typed like profilesApi.ts: the generated client is not committed and
 * nothing imports it. Types mirror AssignmentListView in
 * src/cyo_adventure/api/schemas.py.
 */

import type { AxiosInstance } from 'axios'

export interface AssignmentList {
  storybook_id: string
  profile_ids: string[]
}

export interface AssignApi {
  get(storybookId: string): Promise<string[]>
  add(storybookId: string, profileIds: string[]): Promise<string[]>
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
  }
}
