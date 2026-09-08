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
  // verdict always pairs with null notes; the two states below are the
  // ones that produce it for a cover that reached pending_review (a
  // cover_status === 'failed' row is a separate case: generation's outer
  // error handler rolled back before any review field was written, so
  // its verdict/notes/attempts are also at their zero-value defaults, for
  // a third reason). cover_review_attempts tells the two pending_review
  // states apart, except where noted:
  // - attempts === 0: review did not run at all. EITHER this cover
  //   predates the feature OR the review provider could not be built for
  //   this generation (missing OPENROUTER_API_KEY / unsupported
  //   review_provider setting). These are NOT distinguishable from this
  //   response alone; only a server-side warning log tells them apart.
  // - attempts >= 1: the reviewer ran, and its final attempt returned no
  //   usable verdict (a provider error, an empty/unparseable response, or
  //   a verdict outside pass/flag), which is treated as a pass rather than
  //   blocking publication. This does not mean every attempt failed open:
  //   the bounded loop breaks on any verdict other than "flag", so a
  //   "flag" on an earlier attempt followed by a fail-open on the last
  //   attempt also lands here. A failed-open attempt still increments the
  //   counter, so this is always >= 1 when the reviewer ran at all.
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
