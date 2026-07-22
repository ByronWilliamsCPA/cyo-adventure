/**
 * Version-compare UI state for ReviewDetailPage: fetches the previous
 * version's surface on demand and derives the passage-level diff against the
 * current one. Owns only its own open/loading/diff-result state; the current
 * surface stays owned by ReviewDetailPage's `[state, setState]` and is only
 * ever handed in here as the already-derived, possibly-null `surface`.
 */
import { useCallback, useMemo, useState } from 'react'
import { isAxiosError } from 'axios'

import { classifyApiError } from '../hooks/classifyApiError'
import type { ReviewApi, ReviewSurface } from '../guardian/reviewApi'
import { diffNodes, type VersionDiff } from './reviewDiff'

export type CompareState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'unavailable' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; previous: ReviewSurface }

export interface UseVersionCompareParams {
  storybookId: string
  /** The current ready surface, or null while the surface has not loaded yet. */
  surface: ReviewSurface | null
  reviewApi: ReviewApi
  /** Mount guard shared with the rest of ReviewDetailPage; owned by the parent. */
  isMountedRef: { current: boolean }
}

export interface UseVersionCompareResult {
  compareOpen: boolean
  compareState: CompareState
  /** Opens/closes the panel; a fresh open fetches `surface.version - 1` per the caching rule below. */
  toggleCompare: () => void
  /** The added/changed/removed summary against the current surface, once the previous version has loaded. */
  diff: VersionDiff | null
}

export function useVersionCompare({
  storybookId,
  surface,
  reviewApi,
  isMountedRef,
}: UseVersionCompareParams): UseVersionCompareResult {
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareState, setCompareState] = useState<CompareState>({ kind: 'idle' })

  // #ASSUME: external resources: the previous version may no longer exist
  // (pruned, or the current version is 1 with no version 0 at all); the
  // backend 404s the surface fetch in that case, which axios surfaces as a
  // normal error response, not a thrown/rejected navigation.
  // #ASSUME: timing dependencies: the reviewer can navigate away mid-fetch;
  // isMountedRef (shared with the cover-generation hook) guards every setState
  // after the await so a late response never writes into an unmounted page.
  // #VERIFY: ReviewDetailPage.test.tsx compare tests cover the loading state,
  // the ready diff, and the 404-to-"no longer available" branch.
  const loadCompare = useCallback(
    async (previousVersion: number) => {
      setCompareState({ kind: 'loading' })
      try {
        const previous = await reviewApi.surface(storybookId, previousVersion)
        if (isMountedRef.current) setCompareState({ kind: 'ready', previous })
      } catch (err) {
        console.error('compare version load failed:', err instanceof Error ? err.message : err)
        if (!isMountedRef.current) return
        if (isAxiosError(err) && err.response?.status === 404) {
          setCompareState({ kind: 'unavailable' })
        } else {
          setCompareState({
            kind: 'error',
            message: classifyApiError(err, {
              transient: 'We could not load the previous version for comparison.',
              server: 'We could not load the previous version for comparison.',
            }).message,
          })
        }
      }
    },
    [reviewApi, storybookId, isMountedRef]
  )

  // Toggling closed just hides the panel. A successful ('ready') or
  // permanent (404 'unavailable') outcome stays cached so reopening does not
  // refetch; a transient 'error' is retried on reopen instead, so a network
  // blip does not permanently block comparison for the rest of the page's
  // lifetime the way caching it forever would.
  const toggleCompare = useCallback(() => {
    if (compareOpen) {
      setCompareOpen(false)
      return
    }
    setCompareOpen(true)
    if (surface && (compareState.kind === 'idle' || compareState.kind === 'error')) {
      void loadCompare(surface.version - 1)
    }
  }, [compareOpen, compareState.kind, loadCompare, surface])

  const diff = useMemo<VersionDiff | null>(() => {
    if (!surface || compareState.kind !== 'ready') return null
    return diffNodes(compareState.previous.blob, surface.blob)
  }, [surface, compareState])

  return { compareOpen, compareState, toggleCompare, diff }
}
