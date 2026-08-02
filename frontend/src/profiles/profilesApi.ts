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
  /**
   * W3.4: the RAW stored gamification settings, always present on a
   * ProfileView. `ring_enabled` / `ring_goal_days` are nullable here on
   * purpose (null = no override); see ProfileGamificationFields.
   */
  ring_enabled: boolean | null
  ring_goal_days: number | null
  badges_enabled: boolean
  time_capture_paused: boolean
  created_at: string
}

/**
 * ADR-015 G3 pre-authorization fields (ProfileFormDialog's "Story requests"
 * section).
 *
 * These ARE live server-side now: `ProfileCreateBody` / `ProfileUpdateBody`
 * in `api/schemas.py` declare both, and `create_profile` / `update_profile`
 * (`api/profiles.py`) apply them. An earlier version of this comment warned
 * that sending them 422s the whole request; that gap has since closed, and
 * `apiContractParity.ts` now proves it at compile time rather than leaving
 * the claim to prose that can go stale again.
 *
 * ProfileFormDialog still sends these two keys only when the guardian
 * changes the section from its seeded value, but for a different reason
 * than the old 422 hazard: `monthly_request_envelope` carries PATCH's
 * omitted-vs-explicit-null distinction, so resending an untouched control
 * would turn a no-op edit into a deliberate write.
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

/**
 * W3.4 gamification settings (gamification-recommendation-2026-08-01.md
 * section 4), as the guardian settings form edits them.
 *
 * `ring_enabled` / `ring_goal_days` are the RAW stored values: `null` means
 * "no override, follow the P-A band default", which is a state distinct from
 * an explicit off. The kid-facing RESOLVED values (band defaults already
 * applied) are a different shape and come from `GET /me/progress` instead;
 * see `kid/progressApi.ts`'s `ResolvedGamificationSettings`.
 *
 * #CRITICAL: data-integrity: these live here, on the shared adapter types,
 * rather than as a local mirror in the component that happens to edit them.
 * ProfileFormDialog spreads them into every create and edit body
 * UNCONDITIONALLY, and both bodies are `extra="forbid"` server-side, so a
 * single divergent field name 422s every profile save a guardian makes, not
 * just the gamification section. Declared here they are covered by
 * apiContractParity.ts, which turns that divergence into a `npm run
 * typecheck` failure instead of a runtime 422 nobody sees until a guardian
 * tries to rename their child.
 * #VERIFY: apiContractParity.ts's ProfileCreateBody / ProfileUpdateBody
 * `SendableTo` entries; profilesApi.test.ts pins the wire shape.
 */
export interface ProfileGamificationFields {
  ring_enabled?: boolean | null
  ring_goal_days?: number | null
  badges_enabled?: boolean
  time_capture_paused?: boolean
}

export interface ProfileCreateBody extends ProfileEnvelopeFields, ProfileGamificationFields {
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
export interface ProfileUpdateBody extends ProfileEnvelopeFields, ProfileGamificationFields {
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
  /**
   * P-6c: permanently deletes a child profile. Mirrors DELETE
   * /v1/profiles/{id} (api/profiles.py's delete_profile), which cascades
   * the child's reading state, completions, ratings, assignments, kid
   * flags, and picker-PIN row server-side (GDPR Article 17 / COPPA 312.10);
   * story requests are de-linked, not deleted. The backend has enforced
   * this for a while; only the UI entry point was missing.
   */
  deleteProfile(id: string): Promise<void>
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
    async deleteProfile(id: string): Promise<void> {
      await api.delete(`/v1/profiles/${id}`)
    },
  }
}
