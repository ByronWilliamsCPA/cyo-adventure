/**
 * Adapter for the profile-picker "new story ready!" pill (W1.4, design
 * review 4.1).
 *
 * Hand-typed like profilesApi.ts and childSessionApi.ts's own wire-shape
 * comment: ``GET /v1/profiles/story-status`` is new in this change and has
 * not yet been regenerated into ``src/client/`` (the frontend client is
 * committed and CI fails on drift; regeneration happens centrally). Mirrors
 * ``ProfileStoryStatusView`` / ``ProfileStoryStatusListView`` in
 * ``api/schemas.py``.
 */

import type { AxiosInstance } from 'axios'

/**
 * One profile's pill state. Deliberately boolean-only, matching the
 * backend's own boundary: this endpoint never carries a storybook id,
 * title, or count, so there is nothing here for the picker to leak about a
 * sibling profile beyond "something new happened".
 */
export interface ProfileStoryStatus {
  profile_id: string
  has_new_story: boolean
}

export interface StoryStatusApi {
  /**
   * Bulk "new story ready" status for every profile the calling principal
   * (a device grant, or a guardian who has not yet handed the device off)
   * may list -- the same scope `GET /v1/profiles` already exposes, never
   * wider.
   */
  list(): Promise<ProfileStoryStatus[]>
}

export function makeStoryStatusApi(api: AxiosInstance): StoryStatusApi {
  return {
    async list(): Promise<ProfileStoryStatus[]> {
      const res = await api.get<{ statuses: ProfileStoryStatus[] }>(
        '/v1/profiles/story-status'
      )
      return res.data.statuses
    },
  }
}
