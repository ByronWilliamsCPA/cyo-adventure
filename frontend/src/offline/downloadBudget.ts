/**
 * Offline download budget enforcement (W4.3; media-budget-recommendation-
 * 2026-08-01.md section 2 and section 6's "per-device offline library
 * budget"; owner decision D20).
 *
 * `navigator.storage.estimate()` gates every new story download so a full
 * family tablet degrades to a kid-readable refusal instead of the browser's
 * own all-or-nothing origin eviction silently wiping the whole offline
 * library. Past a 250MB soft cap, the least-recently-opened OTHER cached
 * story is evicted first (D20's "own oldest-unpinned eviction", not the
 * browser's LRU); past a 500MB hard cap with nothing left to evict, the
 * download is refused outright.
 *
 * COORDINATION NOTE: a concurrent change bumps `offline/db.ts`'s
 * `DB_VERSION` and adds a new IndexedDB object store (reading time). This
 * module deliberately touches neither: recency tracking and the refusal
 * flag below live in `localStorage`, not IndexedDB, so this file carries no
 * schema/version surface at all and cannot conflict with that change.
 *
 * #ASSUME data-integrity: there is no "pin" concept anywhere in this
 * codebase today (no favorite/keep-offline flag on a cached book, and no
 * "finished" signal reliably available offline), so eviction is plain
 * least-recently-opened across every cached book, per the task's own
 * fallback instruction ("if no pin concept exists, implement
 * oldest-last-opened eviction with a clear #ASSUME and keep it simple").
 * This also means eviction cannot yet prefer a FINISHED book over an
 * in-progress one, only an older-opened one; the media recommendation's
 * "oldest unpinned finished book" phrasing is honored as far as "oldest
 * unpinned", not "finished", pending a real completion/pin signal.
 */

const DEFAULT_CAP_BYTES = 250 * 1024 * 1024 // 250MB: prefer eviction past here
const HARD_CAP_BYTES = 500 * 1024 * 1024 // 500MB: refuse the download past here

const RECENCY_KEY = 'offline_story_last_opened'
const REFUSAL_KEY = 'offline_download_refusal'
const EVICTION_KEY = 'offline_download_eviction'

/** Kid-facing copy for a refused download, matching the existing kid-language
 * error patterns (short, concrete, names the grown-up as the next step; see
 * e.g. reader/DownloadNeeded.tsx and library/LibraryPage.tsx's EmptyState copy). */
export const OFFLINE_BUDGET_FULL_MESSAGE =
  "This tablet's bookshelf is full. Ask a grown-up to remove a book."

/** Kid-facing copy for a book that was removed to make room for a new one.
 * Eviction is not a failure, so this is framed as information, not an error:
 * the book is still in the library and re-downloads on the next open. */
export const OFFLINE_EVICTION_MESSAGE =
  'We made room for your new book, so an older one is not saved on this tablet anymore. It is still in your library.'

type RecencyMap = Record<string, number>

function readRecency(): RecencyMap {
  try {
    const raw = localStorage.getItem(RECENCY_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    return parsed as RecencyMap
  } catch {
    // #EDGE: browser-compat: storage unavailable or a corrupt blob; treat as
    // "no recency data", which only affects eviction ORDER, never whether
    // enforcement runs at all.
    return {}
  }
}

function writeRecency(map: RecencyMap): void {
  try {
    localStorage.setItem(RECENCY_KEY, JSON.stringify(map))
  } catch {
    // #EDGE: browser-compat: storage unavailable; recency just stops
    // updating, degrading eviction back to "unknown recency" ordering.
  }
}

/**
 * Record that a story (by id; version-independent, matching how eviction
 * operates -- `deleteStorybooksById` removes every cached version of an id)
 * was just opened or downloaded. Call on every successful read of a cached
 * blob AND on every fresh download, so recency reflects actual last-use,
 * not just last-download.
 */
export function recordStoryOpened(id: string): void {
  const map = readRecency()
  map[id] = Date.now()
  writeRecency(map)
}

/** Drop a story's recency entry (called after it is evicted, so a re-download
 * later starts with a clean slate rather than an eviction-time timestamp). */
export function forgetStoryRecency(id: string): void {
  const map = readRecency()
  delete map[id]
  writeRecency(map)
}

/**
 * Pick the least-recently-opened story id from `candidateIds`, excluding
 * `exceptId` (the book currently being downloaded, which must never evict
 * itself). A candidate with no recorded recency (never opened since this
 * map existed -- e.g. cached by a build that predates this feature) sorts
 * as the oldest possible, since "no evidence of recent use" is the safest
 * thing to evict first. Returns null when there is nothing eligible.
 */
export function pickEvictionCandidate(candidateIds: string[], exceptId: string): string | null {
  const map = readRecency()
  const eligible = candidateIds.filter((id) => id !== exceptId)
  if (eligible.length === 0) return null
  return eligible.reduce((oldest, id) => {
    const at = map[id] ?? -Infinity
    const oldestAt = map[oldest] ?? -Infinity
    return at < oldestAt ? id : oldest
  })
}

/** Record that a download was refused for budget reasons, so a kid-facing
 * surface (LibraryPage) can show the refusal copy once, the next time it
 * loads. Consume-once, like a toast. */
export function recordDownloadRefusal(): void {
  try {
    localStorage.setItem(REFUSAL_KEY, String(Date.now()))
  } catch {
    // #EDGE: browser-compat: the refusal itself (skipping the cache write)
    // still happened; only the kid-facing banner is lost, not the
    // enforcement, so this is a UX-only degrade.
  }
}

/** Read and clear the pending download-refusal flag. Returns true at most
 * once per refusal. */
export function consumeDownloadRefusal(): boolean {
  try {
    const raw = localStorage.getItem(REFUSAL_KEY)
    if (!raw) return false
    localStorage.removeItem(REFUSAL_KEY)
    return true
  } catch {
    return false
  }
}

/** Record that a previously-downloaded book was evicted to make room, so the
 * same kid-facing surface can say so once. Separate flag from the refusal:
 * the two outcomes are opposites (the new book WAS saved here) and reporting
 * an eviction as "bookshelf is full" would be wrong. */
export function recordDownloadEviction(): void {
  try {
    localStorage.setItem(EVICTION_KEY, String(Date.now()))
  } catch {
    // #EDGE: browser-compat: same degrade as recordDownloadRefusal -- the
    // eviction happened either way; only the notice is lost.
  }
}

/** Read and clear the pending eviction flag. Returns true at most once per
 * eviction. */
export function consumeDownloadEviction(): boolean {
  try {
    const raw = localStorage.getItem(EVICTION_KEY)
    if (!raw) return false
    localStorage.removeItem(EVICTION_KEY)
    return true
  } catch {
    return false
  }
}

export interface StorageEstimate {
  usage: number
  quota?: number
}

async function estimateUsage(): Promise<StorageEstimate | null> {
  const storage = typeof navigator === 'undefined' ? undefined : navigator.storage
  if (!storage?.estimate) {
    // #EDGE: browser-compat: no StorageManager (older Firefox/Safari). We
    // cannot measure usage, so we cannot enforce a budget against it; fail
    // open rather than block downloads on an unsupported browser.
    return null
  }
  try {
    const estimate = await storage.estimate()
    if (typeof estimate.usage !== 'number') {
      // #EDGE: browser-compat: StorageManager exists but reports no numeric
      // usage. Same fail-open as the missing-API branch, and same reason: a
      // budget cannot be enforced against a number we do not have.
      return null
    }
    return { usage: estimate.usage, quota: estimate.quota }
  } catch (error) {
    // #EDGE: external resources: an API that EXISTS and then throws is a
    // different case from the two above, and it was the only one of the three
    // arriving with no rationale and no trace. Returning null is still the
    // right call (`checkDownloadBudget` maps null to `{ allowed: true }`, so
    // this disables the entire D20 budget: no soft cap, no eviction, no
    // refusal), because blocking a child's downloads over a failed
    // MEASUREMENT would trade a possible quota error for a certain broken
    // feature. What was wrong was doing it invisibly: `db.ts` already logs
    // when `checkDownloadBudget` throws, but swallowing here means that log
    // can never fire, so a browser whose estimate() rejects reads exactly
    // like a browser comfortably under budget. Log, then fail open.
    console.warn('[offline] storage estimate failed; download budget disabled', {
      error,
    })
    return null
  }
}

/**
 * Rough byte size of a JSON-serializable payload, for the pre-write budget
 * check. #ASSUME data-integrity: this estimates the payload's OWN encoded
 * size, not the bytes IndexedDB will actually persist (engine-specific
 * storage overhead, indexes, etc. are not modeled); it is only ever compared
 * against a fixed hundred-plus-MB budget, so being off by a few KB never
 * changes the gate's outcome.
 */
export function estimateByteSize(value: unknown): number {
  try {
    const json = JSON.stringify(value)
    if (typeof TextEncoder !== 'undefined') {
      return new TextEncoder().encode(json).length
    }
    return json.length
  } catch {
    return 0
  }
}

export interface BudgetGateResult {
  /** False only when the download must be refused outright (past the hard
   * cap with nothing left to evict). */
  allowed: boolean
  /** Set when a book should be evicted (by story id) before/alongside the
   * write proceeding. */
  evictStoryId?: string
  /**
   * True when the eviction is the ONLY reason `allowed` is true, i.e. the
   * projected usage is past the hard cap. The caller must treat a failed
   * eviction as a refusal in that case.
   *
   * #CRITICAL: data-integrity: without this the two eviction bands are
   * indistinguishable at the call site, so a failed `deleteStorybooksById`
   * led to caching anyway, knowingly past the hard cap; the next write then
   * hits a real `QuotaExceededError` the budget exists to prevent.
   * #VERIFY: db.test.ts "refuses the write when a required eviction fails".
   */
  evictionRequired?: boolean
}

/**
 * Decide whether caching `newBytes` more data for `storyId` should proceed.
 *
 * `cachedIds` is the caller's current cached-story-id list (from
 * `listCachedStorybookIds()` in db.ts), passed in rather than fetched here
 * so this stays a pure decision function, easy to unit test against a
 * mocked `storage.estimate()`.
 */
export async function checkDownloadBudget(
  storyId: string,
  newBytes: number,
  cachedIds: string[]
): Promise<BudgetGateResult> {
  const estimate = await estimateUsage()
  if (estimate === null) {
    return { allowed: true }
  }
  const projected = estimate.usage + newBytes
  if (projected <= DEFAULT_CAP_BYTES) {
    return { allowed: true }
  }
  const candidate = pickEvictionCandidate(cachedIds, storyId)
  if (projected <= HARD_CAP_BYTES) {
    // Soft-cap band (D20 "prefer evicting"): proceed either way, but evict
    // an old book first when one exists, to keep the buffer under the soft
    // cap for the NEXT download rather than only reacting once the hard cap
    // is actually crossed.
    return candidate ? { allowed: true, evictStoryId: candidate } : { allowed: true }
  }
  // Over the hard cap. #ASSUME data-integrity: this codebase tracks no
  // per-book byte size, only presence, so a single-candidate eviction is a
  // best-effort attempt to get back under budget, not a verified guarantee;
  // "keep it simple" per the task, not a bin-packing solver. Refuse only
  // when there is truly nothing else to evict.
  return candidate
    ? { allowed: true, evictStoryId: candidate, evictionRequired: true }
    : { allowed: false }
}
