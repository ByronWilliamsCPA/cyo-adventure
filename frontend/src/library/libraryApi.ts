import type { AxiosInstance } from 'axios'

/**
 * Hand-typed adapter for the library + ratings endpoints (repo convention:
 * mirror the backend Pydantic views by hand; the generated client is unused).
 * Backend contracts: src/cyo_adventure/api/schemas.py (LibraryItem,
 * LibraryProgress, RatingView).
 */

export interface LibraryProgressView {
  current_node: string
  nodes_visited: number
  updated_at: string
}

export interface LibraryItemView {
  id: string
  title: string
  version: number
  age_band: string
  tier: number
  reading_level_target: number
  node_count: number
  rating: number | null
  progress: LibraryProgressView | null
}

export interface RatingView {
  child_profile_id: string
  storybook_id: string
  value: number
  rated_at: string
  updated_at: string
}

export interface LibraryApi {
  list(profileId: string): Promise<LibraryItemView[]>
  rate(profileId: string, storybookId: string, value: number): Promise<RatingView>
}

export function makeLibraryApi(api: AxiosInstance): LibraryApi {
  return {
    async list(profileId) {
      const res = await api.get<{ stories: LibraryItemView[] }>('/v1/library', {
        params: { profile_id: profileId },
      })
      return res.data.stories
    },
    async rate(profileId, storybookId, value) {
      const res = await api.post<RatingView>('/v1/ratings', {
        profile_id: profileId,
        storybook_id: storybookId,
        value,
      })
      return res.data
    },
  }
}
