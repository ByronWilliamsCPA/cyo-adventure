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
 * it does a single `location.reload()`. A per-chunk sessionStorage flag makes
 * it strictly one-shot, so a chunk that is genuinely, persistently missing
 * (truly offline, asset actually gone) does NOT loop; the second failure falls
 * through to the error boundary instead.
 */

const RELOAD_FLAG_PREFIX = 'chunk-reload:'

export interface ImportWithReloadDeps {
  /** Where the one-shot flag lives; defaults to window.sessionStorage. */
  storage?: Storage
  /** How to reload; defaults to a full window.location.reload(). */
  reload?: () => void
}

/**
 * Testable core of {@link lazyWithReload}. Awaits `factory`; on rejection,
 * force-reloads once (guarded by a per-chunk flag) or, if already reloaded,
 * rethrows so the caller's error boundary can render.
 *
 * On the reload path it returns a promise that never settles: the reload
 * replaces the document before React can render, so nothing should mount from
 * the rejected chunk in the meantime (the Suspense fallback stays up).
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
      ;(deps.reload ?? (() => window.location.reload()))()
      return new Promise<{ default: T }>(() => {})
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
