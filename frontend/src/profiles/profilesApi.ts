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

/** The four content-sensitivity levels (storybook/models.py ContentFlagLevel). */
export const CONTENT_FLAG_LEVELS = ['none', 'mild', 'moderate', 'intense'] as const
export type ContentFlagLevelValue = (typeof CONTENT_FLAG_LEVELS)[number]

/**
 * G2 per-child content-flag ceiling overrides. Each field is undefined/null
 * when the guardian has not set an override for that flag; the child's age
 * band always keeps its own ceiling regardless (a guardian can only tighten
 * it further, never loosen it). Mirrors api/schemas.py ContentFlagCaps.
 */
export interface ContentFlagCaps {
  violence?: ContentFlagLevelValue | null
  scariness?: ContentFlagLevelValue | null
  peril?: ContentFlagLevelValue | null
}

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
  /** G2: per-child content-flag ceiling overrides; always present (an
   *  empty-caps object when the guardian has set none). */
  content_flag_caps: ContentFlagCaps
  /** G2: guardian-set theme exclusions for this child; always present
   *  (an empty array when none are set). */
  banned_themes: string[]
  created_at: string
}

export interface ProfileCreateBody {
  display_name: string
  age_band: AgeBandValue
  reading_level_cap?: number
  avatar?: string | null
  tts_enabled?: boolean
  content_flag_caps?: ContentFlagCaps | null
  banned_themes?: string[] | null
}

/**
 * Deliberately stricter than the backend on the non-avatar fields: the server
 * accepts an explicit null there but treats it as a no-op (see
 * ProfileUpdateBody in schemas.py), so these types keep that confusing shape
 * unrepresentable from the UI. avatar, pin, content_flag_caps, and
 * banned_themes have real "clear via null" semantics.
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
  /**
   * G2: a value REPLACES the stored caps wholesale (not a per-flag merge);
   * an explicit null clears every cap back to "defer to the band ceiling";
   * omitted leaves the stored caps unchanged.
   */
  content_flag_caps?: ContentFlagCaps | null
  /**
   * G2: same replace-not-merge/omit/null-clears contract as
   * content_flag_caps, for the banned-themes exclusion list.
   */
  banned_themes?: string[] | null
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
