/**
 * Cover-generation UI state for ReviewDetailPage: fires the generate POST,
 * polls the status GET until the job leaves 'generating', and seeds the
 * status from the server once the surface is ready. Owns only its own
 * cover-status/busy/timed-out state; the review surface itself stays owned
 * by ReviewDetailPage's `[state, setState]` and is only ever handed in here
 * as the already-derived `readyVersion`.
 */
import { useCallback, useEffect, useState } from 'react'

import type { CoverApi, CoverStatusView } from '../guardian/coverApi'

export interface UseCoverGenerationParams {
  storybookId: string
  /** The ready surface's version, or null while the surface has not loaded yet. */
  readyVersion: number | null
  coverApi: CoverApi
  /** Mount guard shared with the rest of ReviewDetailPage; owned by the parent. */
  isMountedRef: { current: boolean }
}

export interface UseCoverGenerationResult {
  coverStatus: CoverStatusView['cover_status']
  coverBusy: boolean
  coverTimedOut: boolean
  generateCover: () => Promise<void>
}

export function useCoverGeneration({
  storybookId,
  readyVersion,
  coverApi,
  isMountedRef,
}: UseCoverGenerationParams): UseCoverGenerationResult {
  const [coverStatus, setCoverStatus] = useState<CoverStatusView['cover_status']>('none')
  const [coverBusy, setCoverBusy] = useState(false)
  // Set when the poll loop hits its cap while the job is still 'generating', so
  // the reviewer gets a retry affordance instead of a permanently disabled
  // button with no feedback.
  const [coverTimedOut, setCoverTimedOut] = useState(false)

  // Seed the current server-side cover status once the surface is ready, so an
  // in-flight job (e.g. one started in another tab) is reflected and the
  // Generate button is not wrongly enabled. Best-effort: a failure keeps 'none'.
  useEffect(() => {
    if (readyVersion === null) return
    let cancelled = false
    void (async () => {
      try {
        const current = await coverApi.status(storybookId, readyVersion)
        if (!cancelled && isMountedRef.current) setCoverStatus(current.cover_status)
      } catch (err) {
        // Best-effort seed; keep the default status on failure.
        void err
      }
    })()
    return () => {
      cancelled = true
    }
  }, [coverApi, storybookId, readyVersion, isMountedRef])

  // #ASSUME: external resources: cover generation runs async on an RQ worker;
  // the 10s axios timeout in useApi rules out waiting on the POST itself, so
  // this fires the POST then polls the GET status endpoint until it leaves
  // 'generating' (or the poll cap is hit).
  // #VERIFY: coverApi.test.ts covers the request shapes; the isMountedRef
  // guard above stops the loop from writing state after unmount.
  const generateCover = useCallback(async () => {
    if (readyVersion === null) return
    const version = readyVersion
    setCoverBusy(true)
    setCoverTimedOut(false)
    try {
      const started = await coverApi.generate(storybookId, version)
      if (!isMountedRef.current) return
      setCoverStatus(started.cover_status)
      let latest = started.cover_status
      for (let i = 0; i < 30; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        if (!isMountedRef.current) return
        const polled = await coverApi.status(storybookId, version)
        if (!isMountedRef.current) return
        latest = polled.cover_status
        setCoverStatus(latest)
        if (latest !== 'generating') break
      }
      // Poll cap reached with the job still generating: surface a retry
      // affordance rather than a stuck spinner. The backend short-circuits a
      // re-request while still 'generating', so retry cannot duplicate the job.
      if (isMountedRef.current && latest === 'generating') setCoverTimedOut(true)
    } catch (err) {
      // Log the message, not the axios error object (its config.headers
      // carries the caller's Authorization bearer token).
      console.error('cover generation failed:', err instanceof Error ? err.message : err)
      if (isMountedRef.current) setCoverStatus('failed')
    } finally {
      if (isMountedRef.current) setCoverBusy(false)
    }
  }, [coverApi, storybookId, readyVersion, isMountedRef])

  return { coverStatus, coverBusy, coverTimedOut, generateCover }
}
