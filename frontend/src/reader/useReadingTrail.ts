/**
 * Wires the reading-trail recorder into a reader mount (privacy-model.md
 * "Reading trail").
 *
 * The page calls `begin(story, baseline)` once the story is in hand and BEFORE
 * it renders the Reader, because the Reader's own layout effects (an ADR-026
 * flowed opening stop) start sending machine transitions during its first
 * commit, ahead of any effect this hook or the page could register. It then
 * forwards each reported state to `observe`, and calls `leave` on Leave.
 *
 * Everything here is best-effort: no call can throw into the page, nothing is
 * awaited by the reader, and whether the server records anything at all is
 * decided server-side (Settings.reading_trail_enabled).
 */

import { useEffect, useRef, useState } from 'react'

import { sendTrailBatch } from '../offline/readingTrailSync'
import type { ReadingTrailApi } from '../offline/sync'
import { onReaderTransition } from '../player/transitions'
import type { ReadingState, Storybook } from '../player/types'
import { ReadingTrailRecorder } from './readingTrail'

/** How often buffered steps are flushed while the child keeps reading. */
export const TRAIL_FLUSH_INTERVAL_MS = 30_000

export interface UseReadingTrailOptions {
  /** Omitted: nothing is recorded or sent (tests, callers without wiring). */
  api?: ReadingTrailApi
  profileId: string
  storybookId: string
  version: number
}

export interface ReadingTrailHandle {
  begin(story: Storybook, baseline: ReadingState | undefined): void
  observe(state: ReadingState): void
  leave(): void
}

export function useReadingTrail(options: UseReadingTrailOptions): ReadingTrailHandle {
  // The latest options, read at call time, so the returned handle can keep
  // one identity for the life of the mount (ReaderPage lists it in `load`'s
  // dependencies, and a changing identity there would re-fire the load
  // effect; see NO_SERVER_STATE in ReaderPage.tsx for that failure mode).
  const optionsRef = useRef(options)
  useEffect(() => {
    optionsRef.current = options
  })
  const recorderRef = useRef<ReadingTrailRecorder | null>(null)
  const unsubscribeRef = useRef<(() => void) | null>(null)
  // A lazy state initializer, not a ref, so the handle is built once without
  // touching a ref during render; its methods read the refs only when called.
  const [handle] = useState<ReadingTrailHandle>(() => {
    const stop = () => {
      unsubscribeRef.current?.()
      unsubscribeRef.current = null
      recorderRef.current?.leave()
      recorderRef.current = null
    }
    return {
      begin(story: Storybook, baseline: ReadingState | undefined) {
        stop()
        const { api, profileId, storybookId, version } = optionsRef.current
        if (api === undefined) return
        try {
          const recorder = new ReadingTrailRecorder({
            story,
            baseline,
            version,
            send: (body, sendOptions) =>
              sendTrailBatch(api, profileId, storybookId, body, sendOptions),
          })
          recorderRef.current = recorder
          // Filtered by identity: `story` is the very object the page passes
          // to the Reader, which the machine keeps as `context.story`.
          unsubscribeRef.current = onReaderTransition((emitted, transition) => {
            if (emitted === story) recorder.onTransition(transition)
          })
        } catch (error) {
          // #CRITICAL: data-integrity: a recorder fault must never cost the
          // child their book. Log a summary and read on unrecorded.
          // #VERIFY: useReadingTrail.test.ts "keeps reading when the recorder
          // cannot start".
          console.warn('[reading-trail] recorder unavailable', {
            reason: error instanceof Error ? error.name : 'unknown',
          })
          recorderRef.current = null
        }
      },
      observe(state: ReadingState) {
        recorderRef.current?.observe(state)
      },
      leave: stop,
    }
  })

  useEffect(() => {
    const flushTimer = setInterval(() => recorderRef.current?.flush(), TRAIL_FLUSH_INTERVAL_MS)
    // #EDGE: timing: a tab that is closed or discarded never runs React
    // cleanup, so the hide transition is the last reliable moment to send.
    // No leave marker here: hiding is not leaving (the child may come back),
    // so the read stays open and its last step stands as where it stopped.
    // #VERIFY: useReadingTrail.test.ts "flushes with keepalive when the page
    // is hidden".
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') recorderRef.current?.flush({ keepalive: true })
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      clearInterval(flushTimer)
      document.removeEventListener('visibilitychange', onVisibility)
      // Unmount (in-app navigation away, including the browser Back button)
      // is a leave; leave() is idempotent, so a prior Leave tap is not doubled.
      handle.leave()
    }
  }, [handle])

  return handle
}
