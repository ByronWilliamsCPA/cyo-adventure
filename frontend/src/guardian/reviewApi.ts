/**
 * Adapter from the axios instance to the guardian review + approval API (C4a-4).
 *
 * Hand-typed like profilesApi.ts: axios calls here are hand-written (baseURL,
 * auth, and 401 recovery come from useApi()'s instance, not the generated
 * SDK), and most types mirror ReviewQueueItem / ReviewSurfaceView and the
 * approval views in src/cyo_adventure/api/schemas.py by hand. ContentFlags /
 * ContentFlagLevel are the exception: they're re-exported from the generated
 * client (see readingApi.ts / notificationsApi.ts for the same pattern) so a
 * future backend field change can't update the generated type while silently
 * leaving this hand-written mirror behind the OpenAPI drift gate never checks.
 */

import { type AxiosInstance, isAxiosError } from 'axios'

import type {
  ContentFlagLevel,
  ContentFlags,
  FindingSeverity,
  GenerationMeasuresView,
  SafetyConcernCount,
} from '../client/types.gen'

/**
 * Re-exported from the generated client for the reason the module docstring
 * gives for ContentFlags: a hand-written mirror of a backend response type can
 * drift silently, because the OpenAPI drift gate compares the GENERATED files
 * and never sees a hand-typed copy that has fallen behind.
 *
 * `fill_rate` is deliberately nullable on the backend rather than defaulting to
 * zero: a version with no recorded rate (an imported book, or one generated
 * before the rate was stamped) is not a book that filled nothing. Consumers
 * must test for absence explicitly, never for falsiness, since a genuine rate
 * of 0 is a real measurement.
 */
export type {
  ContentFlagLevel,
  ContentFlags,
  FindingSeverity,
  GenerationMeasuresView,
  SafetyConcernCount,
}

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
  report_unusable?: boolean
  block_findings?: number
  flag_findings?: number
  advisory_findings?: number
  summary: ReviewSummary | null
  /** Target age band, for at-a-glance triage (UX-A3). Optional if unknown. */
  age_band?: string | null
  /** When this version was created, a "waiting since" proxy (UX-A3). */
  waiting_since?: string | null
  /** Themes and content-sensitivity flags for the book-detail popover. */
  themes?: string[]
  content_flags?: ContentFlags | null
}

export interface FindingView {
  stage: number
  source: string
  category: string
  node_id: string | null
  verdict: FindingVerdict
  score: number | null
  message: string
  // Additive (Stage B, design doc 2.2/2.6): severity/node_ids come from the
  // post-review merge stage; structural/concern existed on persisted findings
  // since Stage A but were only projected starting with B3. All four are
  // null/false/absent on a pre-Stage-B report.
  severity?: FindingSeverity | null
  node_ids?: string[] | null
  structural?: boolean
  concern?: string | null
}

export interface ValidatorFindingView {
  rule_id: string
  severity: string
  node_id: string | null
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
  report_unusable?: boolean
  summary: ReviewSummary | null
  flagged_passages: FlaggedPassage[]
  story_level_findings: FindingView[]
  // Stage B3 additive fields (design doc 2.6): a flat, non-fanned merged-
  // finding view alongside flagged_passages/story_level_findings above. Each
  // entry still carries node_ids for on-demand drill-down. All four default
  // empty on a pre-B3 backend response or a legacy stored report.
  ranked_findings?: FindingView[]
  structural_findings?: FindingView[]
  low_advisory_findings?: FindingView[]
  validator_findings?: ValidatorFindingView[]
  // R-2: the measurements behind the routing decision. Absent on an older
  // backend response, in which case the console renders no measures block at
  // all rather than an empty one that reads as "nothing was measured".
  generation_measures?: GenerationMeasuresView
}

export interface ApprovedResult {
  id: string
  status: string
  current_published_version: number
  approved_by: string
  published_at: string
  visibility: Visibility
}

/**
 * Closed-vocabulary calibration code for a send-back decision, mirroring
 * SendBackReasonCodeLiteral in src/cyo_adventure/publishing/reason_codes.py
 * (re-exported through api/schemas.py, where it used to live). Kept in sync
 * by hand (this adapter is hand-typed, not generated; see the module
 * docstring above).
 */
export type SendBackReasonCode =
  | 'safety_concern'
  | 'reading_level'
  | 'coherence_error'
  | 'continuity_error'
  | 'weak_choices'
  | 'repetitive'
  | 'prose_quality'
  | 'unsatisfying_ending'
  | 'factual_error'
  | 'other'

export interface SentBackResult {
  id: string
  status: string
  reason: string
  reason_code: SendBackReasonCode
}

/**
 * Result of archiving a published story. Hand-typed to mirror ArchivedView in
 * src/cyo_adventure/api/schemas.py (the same convention as ApprovedResult /
 * SentBackResult above); the backend only ever returns status "archived" here.
 */
export interface ArchivedResult {
  id: string
  status: string
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
  sendBack(
    storybookId: string,
    reason: string,
    reasonCode: SendBackReasonCode
  ): Promise<SentBackResult>
  archive(storybookId: string): Promise<ArchivedResult>
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
    async sendBack(
      storybookId: string,
      reason: string,
      reasonCode: SendBackReasonCode
    ): Promise<SentBackResult> {
      const res = await api.post<SentBackResult>(`/v1/storybooks/${storybookId}/send-back`, {
        reason,
        reason_code: reasonCode,
      })
      return res.data
    },
    // Un-publish a published book: the backend state machine only permits
    // published -> archived (any other status 409s), removing the story from
    // the library. The endpoint takes no body.
    async archive(storybookId: string): Promise<ArchivedResult> {
      const res = await api.post<ArchivedResult>(`/v1/storybooks/${storybookId}/archive`)
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
