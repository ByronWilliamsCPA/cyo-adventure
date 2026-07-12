/**
 * Adapter from the axios instance to the profiles API (C4a-2).
 *
 * Hand-typed like readerApi.ts: the generated client in src/client/ is not
 * committed and nothing imports it. Types mirror ProfileView /
 * ProfileCreateBody / ProfileUpdateBody in src/cyo_adventure/api/schemas.py.
 */

import type { AxiosInstance } from 'axios'

/** The six-band age vocabulary (storybook/models.py AgeBand). */
export const AGE_BANDS = ['3-5', '5-8', '8-11', '10-13', '13-16', '16+'] as const
export type AgeBandValue = (typeof AGE_BANDS)[number]

export interface ProfileView {
  id: string
  display_name: string
  age_band: AgeBandValue
  reading_level_cap: number
  avatar: string | null
  tts_enabled: boolean
  /**
   * Whether a picker PIN is set (P6-07). Derived server-side; the stored
   * hash itself is write-only and never appears in any response.
   */
  has_pin: boolean
  created_at: string
}

export interface ProfileCreateBody {
  display_name: string
  age_band: AgeBandValue
  reading_level_cap?: number
  avatar?: string | null
  tts_enabled?: boolean
}

/**
 * Deliberately stricter than the backend on the non-avatar fields: the server
 * accepts an explicit null there but treats it as a no-op (see
 * ProfileUpdateBody in schemas.py), so these types keep that confusing shape
 * unrepresentable from the UI. Only avatar and pin have real "clear via null"
 * semantics.
 */
export interface ProfileUpdateBody {
  display_name?: string
  age_band?: AgeBandValue
  reading_level_cap?: number
  avatar?: string | null
  tts_enabled?: boolean
  /**
   * Picker PIN (P6-07): a 4-8 digit string sets or replaces it, an explicit
   * null removes it, omitted leaves it unchanged. Never echoed back.
   */
  pin?: string | null
}

export interface ProfilesApi {
  list(): Promise<ProfileView[]>
  create(body: ProfileCreateBody): Promise<ProfileView>
  update(id: string, body: ProfileUpdateBody): Promise<ProfileView>
}

export function makeProfilesApi(api: AxiosInstance): ProfilesApi {
  return {
    async list(): Promise<ProfileView[]> {
      const res = await api.get<{ profiles: ProfileView[] }>('/v1/profiles')
      return res.data.profiles
    },
    async create(body: ProfileCreateBody): Promise<ProfileView> {
      const res = await api.post<ProfileView>('/v1/profiles', body)
      return res.data
    },
    async update(id: string, body: ProfileUpdateBody): Promise<ProfileView> {
      const res = await api.patch<ProfileView>(`/v1/profiles/${id}`, body)
      return res.data
    },
  }
}
