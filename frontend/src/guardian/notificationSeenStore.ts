/**
 * Client-side "seen" tracking for the guardian notification bell (G10).
 *
 * The backend keeps no read/unread state (notifications/service.py's
 * docstring: "unread state is client-side for this first slice"), so the
 * whole read/unread model lives here, in one JSON record per principal:
 *
 * - `lastSeenAt`: the newest `occurred_at` the guardian has had the panel
 *   open for; passed back as the `since` query param so the backend can
 *   compute "what's new" without the client re-deriving it from the full
 *   list.
 * - `toastedIds`: alert-severity notification ids that already fired the
 *   toast channel once, so a poll tick or panel reopen never re-toasts the
 *   same safety event.
 *
 * Every function here is pure aside from the localStorage read/write, and
 * every read/write is wrapped so a guardian in private/locked-down browsing
 * (localStorage throws) degrades to "nothing has been seen yet" rather than
 * crashing the shell -- the same tolerance useApi.ts's token persistence
 * applies to its own localStorage writes.
 */

const MAX_TOASTED_IDS = 100

export interface NotificationSeenRecord {
  lastSeenAt: string | null
  toastedIds: string[]
}

const EMPTY_RECORD: NotificationSeenRecord = { lastSeenAt: null, toastedIds: [] }

function storageKey(principalSubject: string): string {
  return `cyo:notifications:seen:${principalSubject}`
}

function isSeenRecordShape(value: unknown): value is { lastSeenAt: unknown; toastedIds: unknown } {
  return typeof value === 'object' && value !== null && 'toastedIds' in value
}

/**
 * Read the stored record for `principalSubject`, or the empty record when
 * nothing is stored yet, storage is unavailable, or the stored value is not
 * the expected shape (a corrupted or pre-migration value never crashes the
 * bell; it is simply treated as "nothing seen or toasted yet").
 */
export function readSeenRecord(principalSubject: string): NotificationSeenRecord {
  try {
    const raw = localStorage.getItem(storageKey(principalSubject))
    if (raw === null) return EMPTY_RECORD
    const parsed: unknown = JSON.parse(raw)
    if (!isSeenRecordShape(parsed) || !Array.isArray(parsed.toastedIds)) return EMPTY_RECORD
    const lastSeenAt = typeof parsed.lastSeenAt === 'string' ? parsed.lastSeenAt : null
    const toastedIds = parsed.toastedIds.filter((id): id is string => typeof id === 'string')
    return { lastSeenAt, toastedIds }
  } catch {
    return EMPTY_RECORD
  }
}

function writeSeenRecord(principalSubject: string, record: NotificationSeenRecord): void {
  try {
    localStorage.setItem(storageKey(principalSubject), JSON.stringify(record))
  } catch {
    // #EDGE: browser-compat: storage unavailable (private mode / quota). The
    // in-memory state the caller already updated still drives this render;
    // only the next page load loses the update. Mirrors useApi.ts's
    // refresh-token persist-failure tolerance.
  }
}

/**
 * Record that the guardian has seen everything up to `newestOccurredAt`
 * (the panel's newest item at open time). A null/undefined value (an empty
 * panel) leaves the existing `lastSeenAt` untouched rather than clearing it.
 */
export function markSeen(
  principalSubject: string,
  newestOccurredAt: string | null | undefined
): NotificationSeenRecord {
  const current = readSeenRecord(principalSubject)
  const next: NotificationSeenRecord = {
    lastSeenAt: newestOccurredAt ?? current.lastSeenAt,
    toastedIds: current.toastedIds,
  }
  writeSeenRecord(principalSubject, next)
  return next
}

/** Whether `id` has already fired the toast channel for this principal. */
export function hasToasted(principalSubject: string, id: string): boolean {
  return readSeenRecord(principalSubject).toastedIds.includes(id)
}

/**
 * Record that `id` has fired the toast channel, capping the stored id list
 * so a long-lived session's record cannot grow without bound.
 */
export function recordToasted(principalSubject: string, id: string): NotificationSeenRecord {
  const current = readSeenRecord(principalSubject)
  if (current.toastedIds.includes(id)) return current
  const toastedIds = [...current.toastedIds, id].slice(-MAX_TOASTED_IDS)
  const next: NotificationSeenRecord = { ...current, toastedIds }
  writeSeenRecord(principalSubject, next)
  return next
}
