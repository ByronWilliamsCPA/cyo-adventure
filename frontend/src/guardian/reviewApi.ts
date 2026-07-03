/**
 * Adapter from the axios instance to the guardian review + approval API (C4a-4).
 *
 * Hand-typed like profilesApi.ts: the generated client in src/client/ is not
 * committed and nothing imports it. Types mirror ReviewQueueItem /
 * ReviewSurfaceView and the approval views in src/cyo_adventure/api/schemas.py.
 */

import type { AxiosInstance } from 'axios'

export type FindingVerdict = 'block' | 'flag' | 'advisory' | 'pass'

export interface ReviewSummary {
  count: number
  hard_block: boolean
  soft_flag: boolean
  repaired: boolean
  reviewer_independent: boolean
}

export interface ReviewQueueItem {
  storybook_id: string
  title: string
  status: string
  version: number
  screened: boolean
  flagged_count: number
  summary: ReviewSummary | null
}

export interface FindingView {
  stage: number
  source: string
  category: string
  node_id: string | null
  verdict: FindingVerdict
  score: number | null
  message: string
}

export interface FlaggedPassage {
  node_id: string
  prose: string
  findings: FindingView[]
}

export interface ReviewSurface {
  storybook_id: string
  version: number
  status: string
  blob: Record<string, unknown>
  screened: boolean
  summary: ReviewSummary | null
  flagged_passages: FlaggedPassage[]
  story_level_findings: FindingView[]
}

export interface ApprovedResult {
  id: string
  status: string
  current_published_version: number
  approved_by: string
  published_at: string
}

export interface SentBackResult {
  id: string
  status: string
  reason: string
}

/**
 * Shape of a "Still processing" row. The generation-jobs LIST endpoint is
 * C4a-5's (a parallel branch); until it merges stillProcessing() returns [].
 */
export interface StillProcessingItem {
  job_id: string
  title: string
  status: string
}

export interface ReviewApi {
  queue(): Promise<ReviewQueueItem[]>
  surface(storybookId: string, version?: number): Promise<ReviewSurface>
  approve(storybookId: string): Promise<ApprovedResult>
  sendBack(storybookId: string, reason: string): Promise<SentBackResult>
  stillProcessing(): Promise<StillProcessingItem[]>
}

export function makeReviewApi(api: AxiosInstance): ReviewApi {
  return {
    async queue(): Promise<ReviewQueueItem[]> {
      const res = await api.get<{ items: ReviewQueueItem[] }>('/v1/review-queue')
      return res.data.items
    },
    async surface(storybookId: string, version?: number): Promise<ReviewSurface> {
      const res = await api.get<ReviewSurface>(
        `/v1/storybooks/${storybookId}/review`,
        version === undefined ? undefined : { params: { version } }
      )
      return res.data
    },
    async approve(storybookId: string): Promise<ApprovedResult> {
      const res = await api.post<ApprovedResult>(`/v1/storybooks/${storybookId}/approve`)
      return res.data
    },
    async sendBack(storybookId: string, reason: string): Promise<SentBackResult> {
      const res = await api.post<SentBackResult>(`/v1/storybooks/${storybookId}/send-back`, {
        reason,
      })
      return res.data
    },
    // The generation-jobs LIST endpoint is C4a-5's (a parallel branch). Until it
    // merges this returns an empty list so the console's "Still processing"
    // section renders an empty state rather than 404ing. Task 11 wires the real
    // GET once C4a-5 has merged.
    async stillProcessing(): Promise<StillProcessingItem[]> {
      return []
    },
  }
}
