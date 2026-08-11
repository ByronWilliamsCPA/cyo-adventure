/**
 * The country an adult picked on the verification screen, remembered just long
 * enough for the consent form to pre-fill it (ADR-018 D1).
 *
 * Why this exists at all is a database constraint, not a UI preference. KWS
 * needs a location before it will email anyone, but ``User.residence_country``
 * is CHECK-paired to ``consent_accepted_at`` in db/models.py, and consent is
 * two steps further along the sign-in sequence. So the country cannot be
 * persisted where it belongs at the moment it is first needed. The backend
 * snapshots it on the verification attempt row, and this module keeps a copy
 * client-side so the adult is not asked the same question twice minutes apart.
 *
 * It is a CONVENIENCE, never an input to a decision. The value that lands in
 * the database is whatever the consent form submits, and that form remains a
 * required field the adult can change; losing this draft (a different device,
 * a closed tab, a browser that refuses storage) costs one re-pick and nothing
 * else. That is why every operation here swallows its errors: there is no
 * failure mode worth propagating.
 *
 * `sessionStorage` rather than `localStorage` for the same reason
 * parentalGateState.ts uses it: the value belongs to this sign-up attempt in
 * this tab, and a shared or handed-over device should not surface one adult's
 * country to the next one.
 */

const RESIDENCE_DRAFT_KEY = 'cyo.verification.residence-country'

/** Remember the country picked on the verification screen. Never throws. */
export function rememberResidenceDraft(country: string): void {
  try {
    sessionStorage.setItem(RESIDENCE_DRAFT_KEY, country)
  } catch {
    // Storage unavailable (private mode, quota, disabled): the consent form
    // simply starts empty, which is its pre-existing behaviour.
  }
}

/**
 * The remembered country, or '' when there is none.
 *
 * Returns '' rather than null so callers can seed a <select> value directly:
 * '' is already the sentinel for the form's "Select a country" placeholder
 * option, so an absent draft and a never-picked field are the same state.
 */
export function readResidenceDraft(): string {
  try {
    return sessionStorage.getItem(RESIDENCE_DRAFT_KEY) ?? ''
  } catch {
    return ''
  }
}

/** Drop the remembered country. Called on sign-out. Never throws. */
export function clearResidenceDraft(): void {
  try {
    sessionStorage.removeItem(RESIDENCE_DRAFT_KEY)
  } catch {
    // Nothing to clean up if storage is unavailable.
  }
}
