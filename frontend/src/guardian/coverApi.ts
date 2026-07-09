/**
 * Hand-typed adapter for the admin cover endpoints (repo convention: the
 * generated client in src/client/ is unused). Backend: api/covers.py.
 */
import type { AxiosInstance } from 'axios'

export interface CoverStatusView {
  cover_status: 'none' | 'generating' | 'ready' | 'failed'
  cover_url: string | null
}

export interface CoverApi {
  generate: (storybookId: string, version: number) => Promise<CoverStatusView>
  status: (storybookId: string, version: number) => Promise<CoverStatusView>
}

export function makeCoverApi(api: AxiosInstance): CoverApi {
  return {
    async generate(storybookId, version) {
      const res = await api.post<CoverStatusView>(
        `/v1/storybooks/${storybookId}/versions/${version}/cover`,
      )
      return res.data
    },
    async status(storybookId, version) {
      const res = await api.get<CoverStatusView>(
        `/v1/storybooks/${storybookId}/versions/${version}/cover`,
      )
      return res.data
    },
  }
}
