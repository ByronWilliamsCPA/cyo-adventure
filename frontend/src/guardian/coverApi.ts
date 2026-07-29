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
