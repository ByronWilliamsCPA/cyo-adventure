/**
 * Adapter from the axios instance to the guardian review + approval API (C4a-4).
 *
 * Hand-typed like profilesApi.ts: the generated client in src/client/ is not
 * committed and nothing imports it. Types mirror ReviewQueueItem /
 * ReviewSurfaceView and the approval views in src/cyo_adventure/api/schemas.py.
 */

import { type AxiosInstance, isAxiosError } from 'axios'

export type FindingVerdict = 'block' | 'flag' | 'advisory' | 'pass'

export type Visibility = 'family' | 'catalog'

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
  visibility: string
}

export interface SentBackResult {
  id: string
  status: string
  reason: string
}

/**
 * Shape of a "Still processing" row, mapped from a C4a-5 generation-job that is
 * genuinely still generating (queued or running).
 */
export interface StillProcessingItem {
  job_id: string
  title: string
  status: string
}

/**
 * Minimal view of a C4a-5 generation-job row consumed by stillProcessing().
 * Deliberately hand-typed to mirror GenerationJobSummary in intakeApi.ts (the
 * generated client is not committed) without coupling the two adapters. Only
 * the fields this section reads are declared.
 */
interface GenerationJobRow {
  id: string
  status: 'queued' | 'running' | 'passed' | 'needs_review' | 'failed'
  title: string | null
  premise_snippet: string
}

export interface ReviewApi {
  queue(): Promise<ReviewQueueItem[]>
  surface(storybookId: string, version?: number): Promise<ReviewSurface>
  approve(storybookId: string, visibility: Visibility): Promise<ApprovedResult>
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
    async approve(storybookId: string, visibility: Visibility): Promise<ApprovedResult> {
      const res = await api.post<ApprovedResult>(`/v1/storybooks/${storybookId}/approve`, {
        visibility,
      })
      return res.data
    },
    async sendBack(storybookId: string, reason: string): Promise<SentBackResult> {
      const res = await api.post<SentBackResult>(`/v1/storybooks/${storybookId}/send-back`, {
        reason,
      })
      return res.data
    },
    // Wires C4a-5's guardian-only generation-jobs list into the console's
    // "Still processing" section. Only queued/running jobs are genuinely
    // generating: needs_review/passed/failed are terminal or belong in the
    // review queue (per C4a-5's statusPill), so including them here would
    // double-count or mislead.
    //
    // #CRITICAL: security: this endpoint is guardian-only, but the console's
    // primary user is the admin reviewer, for whom queue() succeeds and this
    // 403s. ConsolePage.load() awaits both in one Promise.all, so a reject here
    // would hide the admin's loaded review queue behind the forbidden branch.
    // Swallow every error and return [] so this can never sink the console load.
    // #VERIFY: reviewApi.test.ts asserts a 403 and a generic error both resolve
    // to [] (the deletion-sensitive tests proving this catch is load-bearing).
    async stillProcessing(): Promise<StillProcessingItem[]> {
      try {
        const res = await api.get<{ jobs: GenerationJobRow[] }>('/v1/generation-jobs')
        return res.data.jobs
          .filter((job) => job.status === 'queued' || job.status === 'running')
          .map((job) => ({
            job_id: job.id,
            // Mirror IntakePage: chain with `||` (not `??`) so an empty-string
            // title OR premise_snippet (both reachable backend rows) falls
            // through to the generic label instead of rendering a blank console
            // row. `??` would let a title of "" pass through unblanked.
            title: job.title || job.premise_snippet || 'Untitled request',
            status: job.status,
          }))
      } catch (err) {
        // A 403 is the expected admin outcome (this endpoint is guardian-only)
        // and must resolve to [] so it never sinks the console load; but a 500,
        // network failure, or malformed body should not be invisible. Log
        // anything that is not a 403 before degrading to [].
        if (!(isAxiosError(err) && err.response?.status === 403)) {
          // Log the message, not the axios error object: err.config.headers
          // carries the caller's Authorization bearer token.
          console.error('still-processing load failed:', err instanceof Error ? err.message : err)
        }
        return []
      }
    },
  }
}
