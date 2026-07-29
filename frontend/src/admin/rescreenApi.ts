// Hand-typed adapter like adminLibraryApi.ts / moderationDashboardApi.ts: the
// generated SDK in src/client/sdk.gen.ts is not used; axios calls inherit
// baseURL, auth, timeout, and 401 recovery from useApi()'s instance. Types
// come from the generated client so the OpenAPI drift gate keeps them honest.
import type { AxiosInstance } from 'axios'

import type { BookVerdictView, RescreenSummaryView } from '../client/types.gen'

export type { BookVerdictView, RescreenSummaryView }

const PATH = '/v1/admin/rescreen'

export interface RescreenApi {
  /**
   * Re-run the deterministic policy/band gate and Stage-0 classifiers for a
   * single published storybook (register A4's single-story trigger; a
   * full-catalog sweep is Phase 9 and out of scope here). Scoping to one id
   * mirrors the backend contract: an id that is not currently published is
   * silently skipped, so `results` can come back empty.
   */
  triggerForStorybook(storybookId: string): Promise<RescreenSummaryView>
}

export function makeRescreenApi(api: AxiosInstance): RescreenApi {
  return {
    async triggerForStorybook(storybookId: string): Promise<RescreenSummaryView> {
      const res = await api.post<RescreenSummaryView>(PATH, {
        storybook_ids: [storybookId],
      })
      return res.data
    },
  }
}
