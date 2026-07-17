/**
 * Adapter from the axios instance to the G6 passage-edit API
 * (`PATCH /v1/storybooks/{storybook_id}/versions/{version}/nodes/{node_id}`).
 *
 * Hand-typed like guardian/reviewApi.ts: the generated client in src/client/
 * is not committed and nothing imports it for this endpoint. The success
 * shape mirrors `ReviewSurface` (guardian/reviewApi.ts) exactly, since the
 * backend returns the same refreshed review surface a GET would; this
 * adapter re-exports that type rather than duplicating it so a caller can
 * drop the PATCH result straight into the same state slot as a surface load.
 */

import { type AxiosInstance, isAxiosError } from 'axios'

import type { ReviewSurface } from '../guardian/reviewApi'

export type { ReviewSurface }

/** One deterministic-gate rule failure, shaped like ValidationFinding.to_dict(). */
export interface GateFindingView {
  rule_id: string
  severity: 'error' | 'warning'
  story_id: string
  node_id: string | null
  choice_id: string | null
  message: string
}

export interface NodeEditBody {
  body?: string
  choice_labels?: Record<string, string>
}

/**
 * A 422 gate-failure response, shaped like `core/exceptions.py`'s
 * `ValidationError.to_dict()` with `details.findings` populated by
 * `node_edit.py::edit_node`. `null` when the response is not this specific
 * shape (a different error, or no response at all).
 */
export interface GateFailure {
  message: string
  findings: GateFindingView[]
}

/**
 * Narrow an unknown thrown value to a G6 gate-failure body, or ``null``.
 *
 * Only a 422 whose body carries `details.findings` as an array counts: any
 * other status, or a 422 shaped differently (e.g. FastAPI's own request-body
 * validation envelope, `{"detail": [...]}`), returns ``null`` so the caller
 * falls back to its generic error handling instead of rendering a
 * malformed/empty rule list.
 */
export function asGateFailure(err: unknown): GateFailure | null {
  if (!isAxiosError(err) || err.response?.status !== 422) return null
  const data: unknown = err.response.data
  if (typeof data !== 'object' || data === null) return null
  const record = data as Record<string, unknown>
  const details = record.details
  if (typeof details !== 'object' || details === null) return null
  const findings = (details as Record<string, unknown>).findings
  if (!Array.isArray(findings)) return null
  const message = typeof record.message === 'string' ? record.message : 'Edit rejected.'
  return { message, findings: findings as GateFindingView[] }
}

export interface PassageEditApi {
  editNode(
    storybookId: string,
    version: number,
    nodeId: string,
    body: NodeEditBody,
  ): Promise<ReviewSurface>
}

export function makePassageEditApi(api: AxiosInstance): PassageEditApi {
  return {
    async editNode(
      storybookId: string,
      version: number,
      nodeId: string,
      body: NodeEditBody,
    ): Promise<ReviewSurface> {
      const res = await api.patch<ReviewSurface>(
        `/v1/storybooks/${storybookId}/versions/${version}/nodes/${encodeURIComponent(nodeId)}`,
        body,
      )
      return res.data
    },
  }
}
