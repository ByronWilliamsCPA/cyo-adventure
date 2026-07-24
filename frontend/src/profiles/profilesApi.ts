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
   * Guardian-set per-child motion preference: when true, the kid surface
   * treats this child's session as if prefers-reduced-motion were set,
   * regardless of the device's own OS-level preference (band-tokens.css).
   */
  reduce_motion: boolean
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

/**
 * ADR-015 G3 pre-authorization fields (ProfileFormDialog's "Story requests"
 * section).
 *
 * #CRITICAL: external-resources: at this writing, POST /v1/profiles and
 * PATCH /v1/profiles/{id} (api/schemas.py's ProfileCreateBody /
 * ProfileUpdateBody) do NOT declare these two fields, and both bodies use
 * `extra="forbid"` server-side -- sending them today 422s the WHOLE
 * request, not just these keys. The DB column and the read-only usage view
 * (`ChildEnvelopeUsageView`, surfaced only via GET /v1/families/me/budget)
 * exist, but the write path into a profile does not yet. ProfileFormDialog
 * only includes these keys in a create/update body when the guardian
 * actually changes this section from its seeded value (see its "touched"
 * gate), so an ordinary profile edit that never opens this section is
 * unaffected either way; a guardian who DOES use it will 422 until a
 * backend change adds these fields to ProfileCreateBody/ProfileUpdateBody
 * and applies them in create_profile/update_profile (api/profiles.py).
 * #VERIFY: profilesApi.test.ts pins the wire shape only; closing the gap
 * itself is backend work tracked outside this change.
 */
export interface ProfileEnvelopeFields {
  /** Whether this child's story requests skip the guardian's own click. */
  request_auto_approve?: boolean
  /**
   * The monthly cap (in stories) auto-approval may spend for this child.
   * `null` means "no envelope set", which blocks auto-approval even when
   * `request_auto_approve` is true -- never "unlimited".
   */
  monthly_request_envelope?: number | null
}

export interface ProfileCreateBody extends ProfileEnvelopeFields {
  display_name: string
  age_band: AgeBandValue
  reading_level_cap?: number
  avatar?: string | null
  tts_enabled?: boolean
  reduce_motion?: boolean
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
export interface ProfileUpdateBody extends ProfileEnvelopeFields {
  display_name?: string
  age_band?: AgeBandValue
  reading_level_cap?: number
  avatar?: string | null
  tts_enabled?: boolean
  reduce_motion?: boolean
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
