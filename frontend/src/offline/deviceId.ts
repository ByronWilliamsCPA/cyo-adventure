/**
 * G15 storage/download view: a persistent, client-generated device identity.
 *
 * Deliberately NOT `device_grant`'s `jti` (the kid-mode device-authorization
 * token id, `auth/deviceGrant.ts`): a guardian's own browser previewing the
 * kid shelf downloads books too and holds no device grant of its own, so
 * keying the download report on the auth token id would silently miss it.
 * This id exists purely to answer "which physical device is this", and
 * outlives any one login session.
 */

const STORAGE_KEY = 'cyo_device_id'

/**
 * Return this browser's persistent device id, minting and storing one via
 * `crypto.randomUUID()` on first use (mirrors `offline/sync.ts`'s own
 * `newId` default).
 *
 * localStorage, not IndexedDB: this is a single small string read
 * synchronously on nearly every reporting call, and unlike the `storybooks`/
 * `reading_states` stores, it holds no data that needs `db.ts`'s
 * transactional guarantees.
 *
 * #CRITICAL: external-resources: called synchronously from ReaderRoute's
 * reportDownload, itself invoked from ReaderPage.tsx's load() with no
 * surrounding try/catch (every OTHER step in load() is individually
 * guarded). Safari private browsing throws QuotaExceededError on
 * localStorage.setItem with a 0-byte quota; an unguarded throw here would
 * propagate out of load(), which runs as bare `void load()` in a mount
 * effect, so the page would never reach `setPageState({ phase: 'reading' })`
 * and would stay on the loading screen forever with no error and no retry.
 * Falling back to an ungenerated (session-only, not persisted) id keeps this
 * function's contract -- always returns a usable id, never throws -- true
 * even when storage is unavailable.
 * #VERIFY: deviceId.test.ts "falls back to an ephemeral id when localStorage
 * throws".
 */
export function getOrCreateDeviceId(): string {
  try {
    const existing = localStorage.getItem(STORAGE_KEY)
    if (existing) return existing
    const fresh = crypto.randomUUID()
    localStorage.setItem(STORAGE_KEY, fresh)
    return fresh
  } catch {
    return crypto.randomUUID()
  }
}
