/**
 * Hand-typed adapter for the admin cover endpoints (repo convention: the
 * generated client in src/client/ is unused). Backend: api/covers.py.
 */
import type { AxiosInstance } from 'axios'

export interface CoverStatusView {
  cover_status: 'none' | 'generating' | 'pending_review' | 'ready' | 'failed'
  cover_url: string | null
  // Present (non-null) only once an admin has approved a pending_review
  // cover via POST .../cover/approve (H2, covers.service.approve_cover);
  // absent from the wire response entirely for a pre-approval status, so
  // both fields default undefined rather than null. A16 (capability-register.md).
  cover_approved_by?: string | null
  cover_approved_at?: string | null
  // AI cover reviewer outcome for the surviving generation attempt
  // (docs/superpowers/specs/2026-09-08-cover-ai-review-design.md). A null
  // verdict always pairs with null notes; cover_review_attempts tells the
  // two states apart, except where noted:
  // - attempts === 0: review did not run at all. EITHER this cover
  //   predates the feature OR the review provider could not be built for
  //   this generation (missing OPENROUTER_API_KEY / unsupported
  //   review_provider setting). These are NOT distinguishable from this
  //   response alone; only a server-side warning log tells them apart.
  // - attempts >= 1: the reviewer ran, and every attempt failed open (the
  //   reviewer call errored and was treated as a pass). A failed-open
  //   attempt still increments the counter, so this is always >= 1 when
  //   the reviewer ran at all.
  cover_review_verdict: 'pass' | 'flag' | null
  cover_review_notes: string | null
  cover_review_attempts: number
}

export interface CoverApi {
  generate: (storybookId: string, version: number) => Promise<CoverStatusView>
  status: (storybookId: string, version: number) => Promise<CoverStatusView>
  approve: (storybookId: string, version: number) => Promise<CoverStatusView>
}

export function makeCoverApi(api: AxiosInstance): CoverApi {
  return {
    async generate(storybookId, version) {
      const res = await api.post<CoverStatusView>(
        `/v1/storybooks/${storybookId}/versions/${version}/cover`
      )
      return res.data
    },
    async status(storybookId, version) {
      const res = await api.get<CoverStatusView>(
        `/v1/storybooks/${storybookId}/versions/${version}/cover`
      )
      return res.data
    },
    async approve(storybookId, version) {
      // Admin-only (api/covers.py::approve_cover); the backend re-checks
      // is_admin regardless of what the console's own role gating shows, so
      // a non-admin call still 403s server-side (A16's authz boundary).
      const res = await api.post<CoverStatusView>(
        `/v1/storybooks/${storybookId}/versions/${version}/cover/approve`
      )
      return res.data
    },
  }
}
