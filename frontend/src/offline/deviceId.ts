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
 * Per-session identity used when localStorage is unreadable or unwritable.
 * Held at module scope so repeat calls within one page life return the same
 * id (the download report groups by it); it simply does not survive a reload
 * the way the stored one does.
 */
let sessionDeviceId: string | undefined

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
 * Never throws. Callers report downloads fire-and-forget from inside the
 * reader's load path, so a storage failure here must degrade the guardian's
 * download view, never the child's ability to read.
 */
export function getOrCreateDeviceId(): string {
  // #CRITICAL: external resources: localStorage is not always available even
  // when the object exists. Safari private browsing hands back a store with a
  // zero-byte quota whose setItem throws QuotaExceededError, and a
  // cookies-blocked profile or storage-blocking extension can throw
  // SecurityError on plain getItem. This is called synchronously from
  // ReaderRoute's reportDownload, itself invoked from ReaderPage's load(),
  // which runs as a bare `void load()` in a mount effect: an uncaught throw
  // here would abort the load before it reaches
  // setPageState({ phase: 'reading' }), stranding the reader on the loading
  // screen forever with no error and no retry.
  // #VERIFY: deviceId.test.ts "still returns an id, instead of throwing, when
  // localStorage.getItem throws" and "still returns a stable id, from the
  // in-memory fallback, when localStorage.setItem throws".
  try {
    const existing = localStorage.getItem(STORAGE_KEY)
    if (existing) return existing
  } catch {
    // Unreadable storage: fall through to the in-memory identity.
  }
  sessionDeviceId ??= crypto.randomUUID()
  try {
    localStorage.setItem(STORAGE_KEY, sessionDeviceId)
  } catch {
    // Unwritable storage: the id stays session-scoped. The guardian's view
    // then shows this device as a new entry per session, which is a degraded
    // but honest signal; blocking the read would not be.
  }
  return sessionDeviceId
}
