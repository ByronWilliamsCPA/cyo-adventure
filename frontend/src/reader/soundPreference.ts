/**
 * Client-side persistence for the reader's sound-effects mute toggle (W4.2,
 * D7), mirroring `kid/readAloudPreference.ts`'s single-slot
 * {@link https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage localStorage}
 * cache pattern (same key shape, same fail-safe-hidden error handling).
 *
 * #ASSUME: data-integrity: `ReaderChrome.tsx` (the only reader file this
 * change may touch) has no `profileId` in its current props, and the only
 * place that could thread one through -- `Reader.tsx` -- is out of scope for
 * this change (a concurrent agent owns it). Every call site therefore passes
 * `DEVICE_PREFERENCE_KEY` today, so in practice this is one device-level
 * mute preference, not truly per-profile, even though the storage shape
 * below is already profile-keyed. `ReaderChromeProps.profileId` is wired as
 * an optional prop for exactly this reason: the moment a future change
 * threads a real profile id through, per-profile scoping activates with no
 * further change here. This is a real limitation, not a hidden one: it is
 * called out again at the `profileId` prop itself.
 */

const KEY = 'reader_sound_muted'

/** Sentinel profile id used whenever no real profile id is available. */
export const DEVICE_PREFERENCE_KEY = '__device__'

interface StoredPreference {
  profileId: string
  muted: boolean
}

function isStoredPreference(value: unknown): value is StoredPreference {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return typeof candidate.profileId === 'string' && typeof candidate.muted === 'boolean'
}

/**
 * Persist the mute choice for a profile (or {@link DEVICE_PREFERENCE_KEY}).
 * #EDGE: browser-compat: localStorage.setItem throws in private/locked-down
 * browser modes; the mute toggle just will not persist across a reload for
 * this session, which degrades to "always defaults fresh" rather than
 * throwing out of the toggle's click handler.
 */
export function setSoundMutedPreference(profileId: string, muted: boolean): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ profileId, muted }))
  } catch {
    // #EDGE: browser-compat: storage unavailable; nothing more to do here.
  }
}

/**
 * Read back the stored mute choice for the given profile id (or
 * {@link DEVICE_PREFERENCE_KEY}). Returns `undefined` when there is no
 * stored value, the stored value belongs to a DIFFERENT profile/key, or
 * storage/parsing fails for any reason -- `undefined` is distinct from an
 * explicit `false` so the caller can apply its own default (sound on,
 * except a reduce_motion default of muted) only when nothing was ever
 * explicitly chosen.
 */
export function getSoundMutedPreference(profileId: string): boolean | undefined {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return undefined
    const parsed: unknown = JSON.parse(raw)
    if (!isStoredPreference(parsed)) return undefined
    return parsed.profileId === profileId ? parsed.muted : undefined
  } catch {
    // #EDGE: browser-compat: storage unavailable, or a corrupt/partial blob
    // that failed to parse; either way, fall back to the caller's default.
    return undefined
  }
}
