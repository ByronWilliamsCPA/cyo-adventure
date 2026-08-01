/**
 * Adapter for the profile-picker "new story ready!" pill (W1.4, design
 * review 4.1).
 *
 * Hand-typed like profilesApi.ts and childSessionApi.ts. The generated
 * client has since been regenerated and includes this route
 * (``ProfileStoryStatusView`` / ``ProfileStoryStatusListView`` in
 * ``src/client/types.gen.ts``); this adapter is retained for its defensive
 * malformed-response handling. Follow-up: assert parity in
 * ``apiContractParity.ts``.
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
      // #ASSUME: data-integrity: a malformed/missing `statuses` array (a
      // stale mock in a test, or a future backend contract change) degrades
      // to "no pills" here rather than throwing, so a shape mismatch on this
      // purely decorative signal can never surface as an error to the
      // picker (ProfilePickerPage.tsx's caller already treats any rejection
      // the same way; this just widens that same posture to a malformed
      // 200).
      // #VERIFY: storyStatusApi.test.ts::"tolerates a missing statuses array".
      return Array.isArray(res.data.statuses) ? res.data.statuses : []
    },
  }
}
