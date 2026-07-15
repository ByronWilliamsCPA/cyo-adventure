import { lazy } from 'react'
import type { ComponentType, LazyExoticComponent } from 'react'

/**
 * Route-chunk loading with one-shot stale-deploy recovery.
 *
 * The app is code-split by audience (routeElements.tsx). Chunk filenames are
 * content-hashed, so a deploy renames them. A returning client whose service
 * worker still serves the previous app shell references the OLD hashes; the
 * first cross-chunk client-side navigation then dynamic-imports a filename the
 * new deploy deleted, the import 404s, and React drops into the route error
 * boundary ("Something went wrong"). A plain browser reload fixes it (it
 * fetches the fresh index.html and current hashes), but users see a crash
 * first and many will not think to reload.
 *
 * `lazyWithReload` forces that reload automatically: on the first failed import
 * it does a single `location.reload()`. Three guards keep the recovery narrow
 * and loop-free:
 *
 * 1. It only reloads for a chunk-LOAD failure (the stale-deploy signature). A
 *    transient error a reload cannot fix (and would only compound by discarding
 *    unsaved in-page state) falls straight through to the error boundary.
 * 2. A per-chunk sessionStorage flag makes it strictly one-shot, so a chunk that
 *    is genuinely, persistently missing (truly offline, asset actually gone)
 *    does NOT loop; the second failure falls through to the error boundary.
 * 3. A watchdog surfaces the error if the reload turns out to be a no-op (a
 *    blocked or suppressed navigation) instead of hanging the Suspense fallback
 *    forever.
 */

const RELOAD_FLAG_PREFIX = 'chunk-reload:'

// How long to wait for the forced reload to replace the document before giving
// up and surfacing the error to the boundary. A real reload tears down the page
// long before this fires; the timeout only matters when the reload was a no-op.
const DEFAULT_WATCHDOG_MS = 10_000

export interface ImportWithReloadDeps {
  /** Where the one-shot flag lives; defaults to window.sessionStorage. */
  storage?: Storage
  /** How to reload; defaults to a full window.location.reload(). */
  reload?: () => void
  /** Watchdog grace period in ms; defaults to {@link DEFAULT_WATCHDOG_MS}. */
  watchdogMs?: number
  /**
   * Schedules the watchdog; defaults to window.setTimeout. Injectable so tests
   * can drive the no-op-reload path deterministically without real timers.
   */
  setTimer?: (callback: () => void, ms: number) => void
}

/**
 * Recognizes the stale-deploy chunk-load failure. Vite/Rollup surface a missing
 * dynamic chunk as a TypeError whose message contains "Failed to fetch
 * dynamically imported module" (Chrome/Safari) or "error loading dynamically
 * imported module" (Firefox); webpack-style bundlers use a `ChunkLoadError`
 * name. Anything else (an app-level throw inside the module, a genuinely
 * transient network error mid-read) is NOT recoverable by a hard reload.
 */
function isChunkLoadError(error: unknown): error is Error {
  if (!(error instanceof Error)) return false
  if (error.name === 'ChunkLoadError') return true
  return /(?:failed to fetch|error loading) dynamically imported module/i.test(error.message)
}

/**
 * Testable core of {@link lazyWithReload}. Awaits `factory`; on a stale-deploy
 * chunk-load rejection, force-reloads once (guarded by a per-chunk flag) or, if
 * already reloaded, rethrows so the caller's error boundary can render. Any
 * non-chunk-load rejection is rethrown immediately without reloading.
 *
 * On the reload path it returns a promise that only settles via the watchdog: a
 * successful reload replaces the document before React can render, so nothing
 * mounts from the rejected chunk in the meantime (the Suspense fallback stays
 * up). If the reload is a no-op, the watchdog rejects with the original error.
 */
export async function importWithReload<T>(
  chunkName: string,
  factory: () => Promise<{ default: T }>,
  deps: ImportWithReloadDeps = {}
): Promise<{ default: T }> {
  const flag = `${RELOAD_FLAG_PREFIX}${chunkName}`
  try {
    const mod = await factory()
    // #ASSUME: external-resources: a successful load means the current shell
    // and this chunk agree, so clear the one-shot flag to re-arm recovery for
    // any future stale-deploy failure this session.
    // #VERIFY: lazyWithReload.test.ts "clears the reload flag on success".
    tryStorage(() => (deps.storage ?? window.sessionStorage).removeItem(flag))
    return mod
  } catch (error) {
    // #ASSUME: external-resources: only a stale-deploy chunk-LOAD failure is
    // recoverable by reloading. A module-level throw or a transient network
    // error is not fixed by a hard reload, which would also discard any
    // unsaved in-page state (e.g. a child's reading progress), so those route
    // straight to the error boundary instead of triggering a reload.
    // #VERIFY: lazyWithReload.test.ts "does not reload on a non-chunk error".
    if (!isChunkLoadError(error)) {
      throw error
    }
    // #CRITICAL: external-resources: recover from a stale-deploy chunk 404 with
    // exactly ONE hard reload. The flag guard is what prevents an infinite
    // reload loop when the asset is truly gone or the device is offline; if
    // storage itself is unavailable we must NOT reload (we could not record the
    // attempt), so we fall through to the error boundary instead.
    // #VERIFY: lazyWithReload.test.ts covers first-failure-reloads,
    // second-failure-throws, and storage-unavailable-does-not-reload.
    const alreadyReloaded = tryStorage(() => {
      const store = deps.storage ?? window.sessionStorage
      if (store.getItem(flag) !== null) return true
      store.setItem(flag, '1')
      return false
    })
    if (alreadyReloaded === false) {
      // Observability: a stale-deploy recovery is otherwise invisible in prod
      // (the reload discards the console). Log before reloading so the intent
      // is captured, and again from the watchdog if the reload never lands.
      console.warn(`lazyWithReload: forcing one reload to recover stale chunk "${chunkName}"`)
      ;(deps.reload ?? (() => window.location.reload()))()
      // #CRITICAL: timing-dependencies: a real reload replaces the document
      // before this watchdog fires. If the reload was a no-op (blocked or
      // suppressed navigation), reject after a grace period so the error
      // boundary renders instead of the Suspense fallback hanging forever.
      // #VERIFY: lazyWithReload.test.ts "rejects via the watchdog when the
      // reload does not replace the document".
      return new Promise<{ default: T }>((_resolve, reject) => {
        const schedule = deps.setTimer ?? ((callback, ms) => void window.setTimeout(callback, ms))
        schedule(() => {
          console.error(
            `lazyWithReload: reload did not recover chunk "${chunkName}"; surfacing the error`
          )
          reject(error)
        }, deps.watchdogMs ?? DEFAULT_WATCHDOG_MS)
      })
    }
    throw error
  }
}

/**
 * Run a storage operation, returning its result, or `null` if storage access
 * throws (hardened privacy modes). A `null` return on the failure path means
 * "could not use storage", which the caller treats as "do not reload".
 */
function tryStorage<R>(op: () => R): R | null {
  try {
    return op()
  } catch {
    return null
  }
}

/**
 * Drop-in replacement for React.lazy that adds stale-deploy reload recovery.
 * `chunkName` only needs to be unique per lazy component (it keys the one-shot
 * flag); the export name is the natural choice.
 */
// The `any` mirrors React.lazy's own signature (`<T extends ComponentType<any>>`);
// a narrower bound (e.g. ComponentType<never>) is not assignable to it, so a
// scoped exception is the honest way to pass a component type through unchanged.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyWithReload<T extends ComponentType<any>>(
  chunkName: string,
  factory: () => Promise<{ default: T }>
): LazyExoticComponent<T> {
  return lazy(() => importWithReload(chunkName, factory))
}
