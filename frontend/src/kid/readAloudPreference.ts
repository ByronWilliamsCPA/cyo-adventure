/**
 * Client-side cache of a picked profile's `tts_enabled` flag (K7 / Phase 4b
 * read-aloud), scoped to whichever profile was most recently picked.
 *
 * The reader route (`/read/:profileId/:storybookId/:version`) only ever
 * receives a profile id, never the full `ProfileView`, so it cannot know on
 * its own whether the read-aloud toggle should appear. `GET /v1/profiles`
 * (which `ProfilePickerPage` already fetches to render the picker grid)
 * already returns `tts_enabled` per profile; rather than adding a second
 * fetch on every reader page load (or a backend change), the picker persists
 * the flag here at pick time, alongside the child session it mints
 * (`../auth/childSession.ts`). `ReaderRoute` reads it back by profile id.
 *
 * This is a companion cache, not a security boundary: it only ever gates
 * whether a UI control is offered, never an authorization decision, so a
 * stale or missing value degrades to "no read-aloud button" rather than to
 * any unsafe default.
 */

const KEY = 'child_session_read_aloud'

interface StoredPreference {
  profileId: string
  ttsEnabled: boolean
}

function isStoredPreference(value: unknown): value is StoredPreference {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.profileId === 'string' && typeof candidate.ttsEnabled === 'boolean'
  )
}

/**
 * Persist the `tts_enabled` flag for the profile a child just picked. Call
 * this alongside `setChildSession` (`ProfilePickerPage`'s pick handlers), not
 * as its own independent flow.
 *
 * #EDGE: browser-compat: localStorage.setItem throws in private/locked-down
 * browser modes. That just means the read-aloud toggle will not appear for
 * this session (the same safe-hidden degradation as an unsupported browser);
 * it must never throw out of the picker's click handler.
 */
export function setReadAloudPreference(profileId: string, ttsEnabled: boolean): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ profileId, ttsEnabled }))
  } catch {
    // #EDGE: browser-compat: storage unavailable; nothing more to do here.
  }
}

/**
 * Read back the stored `tts_enabled` flag for the given profile id. Returns
 * false (hide the toggle) whenever there is no stored value, the stored
 * value belongs to a DIFFERENT profile (e.g. a deep link opened without
 * going through the picker), or storage/parsing fails for any reason.
 */
export function getReadAloudPreference(profileId: string): boolean {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return false
    const parsed: unknown = JSON.parse(raw)
    if (!isStoredPreference(parsed)) return false
    return parsed.profileId === profileId ? parsed.ttsEnabled : false
  } catch {
    // #EDGE: browser-compat: storage unavailable, or a corrupt/partial blob
    // that failed to parse; either way, hide the toggle rather than guess.
    return false
  }
}
