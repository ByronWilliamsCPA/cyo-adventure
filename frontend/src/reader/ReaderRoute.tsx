import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'

import { EmptyState } from '@ds/components/EmptyState'
import { Button } from '@ds/components/Button'
import { getValidChildSession } from '../auth/childSession'
import {
  makeFetchReadingHistory,
  makeFetchServerState,
  makeFetchSeriesNext,
  makeFetchStory,
  makeRecordCompletion,
  makeSubmitFlag,
  makeSyncApi,
} from '../api/readerApi'
import { makeFetchPersonalizationValues } from '../api/personalizationApi'
import { isPersonalizationEnabled } from '../env'
import { useApi } from '../hooks/useApi'
import { useReplayOnReconnect } from '../hooks/useReplayOnReconnect'
import { getReadAloudPreference } from '../kid/readAloudPreference'
import { useToast } from '../notifications/useToast'
import { clearPersonalizationValues, getCachedPersonalizationValues } from '../offline/db'
import { type ReplayOutcome } from '../offline/sync'
import { reconcilePersonalizationValues } from '../offline/revocation'
import { parseContinuation } from '../player/series'
import { KID_PICKER_PATH } from '../routes'
import { BackToLibrary } from './BackToLibrary'
import { ReaderPage } from './ReaderPage'

// #ASSUME: security: router location.state is untrusted input, same caveat as
// parseContinuation in player/series.ts (any page can craft it via history
// manipulation). Only a literal boolean at the expected key is accepted;
// anything else (missing key, wrong type, a forged non-boolean) reads as
// undefined ("unknown"), which is exactly the pre-D8 behavior: the values
// fetch is still attempted. Only an explicit `false` ever skips it.
// #VERIFY: ReaderRoute.test.tsx "ReaderRoute personalization eligibility
// route state (D8)".
function parsePersonalizationEligibleState(state: unknown): boolean | undefined {
  if (typeof state !== 'object' || state === null) return undefined
  const flag = (state as { personalizationEligible?: unknown }).personalizationEligible
  return typeof flag === 'boolean' ? flag : undefined
}

/**
 * Router-driven entry point for the reader, migrated off App.tsx's former
 * hard-coded demo config onto real route params: /read/:profileId/:storybookId/:version.
 *
 * Kid auth (which profile/story a session may open) is C4a-2's job, not
 * this route's; this stays unauthenticated for now, matching the pre-router
 * behavior it replaces.
 */
export function ReaderRoute() {
  const { profileId, storybookId, version } = useParams<{
    profileId: string
    storybookId: string
    version: string
  }>()
  const api = useApi()
  // ADR-023 Task D8: read ahead of the fetchPersonalizationValues memo below
  // (which closes over it), so location must be resolved here rather than
  // further down where the rest of the route's useLocation() call used to
  // live.
  const location = useLocation()
  const personalizationEligible = useMemo(
    () => parsePersonalizationEligibleState(location.state),
    [location.state]
  )
  const syncApi = useMemo(() => makeSyncApi(api), [api])
  const fetchStory = useMemo(() => makeFetchStory(api), [api])
  // Memoized like syncApi/fetchStory above, keyed on the same stable `api`
  // instance: ReaderPage's load() useCallback depends on fetchServerState by
  // identity, so a non-memoized factory call here would mint a fresh function
  // every render and re-fire the mount effect in an unbounded loop (see the
  // NO_SERVER_STATE/NO_RECORD_COMPLETION comment in ReaderPage.tsx for the
  // regression this pattern guards against).
  const fetchServerState = useMemo(() => makeFetchServerState(api), [api])
  const recordCompletion = useMemo(() => makeRecordCompletion(api), [api])
  const fetchSeriesNext = useMemo(() => makeFetchSeriesNext(api), [api])
  const fetchReadingHistory = useMemo(() => makeFetchReadingHistory(api), [api])
  const submitFlag = useMemo(() => makeSubmitFlag(api), [api])
  // ADR-023 P6. Memoized on the stable `api` identity like every port above it:
  // ReaderPage's load() depends on these by identity, so a fresh function per
  // render re-fires its mount effect in an unbounded loop (see the
  // NO_SERVER_STATE/NO_RECORD_COMPLETION comment in ReaderPage.tsx for the
  // regression this pattern guards against).
  //
  // Undefined, not a no-op function, when the flag is off: ReaderPage's prop is
  // optional and an absent prop is what makes "no fetch and no cache read" the
  // structural default rather than a branch someone can accidentally invert.
  const fetchPersonalizationValues = useMemo(() => {
    if (!isPersonalizationEnabled()) return undefined
    const fetchValues = makeFetchPersonalizationValues(api)
    return async (storybookId: string) => {
      // ADR-023 Task D8 (closes Stage C open question 2): when the library
      // listing said this book carries no personalizable slots at all
      // (personalization_eligible === false, threaded through router state
      // by BookCard), skip the network fetch AND the cache read entirely
      // instead of making a round trip that could only ever come back
      // empty. Only an explicit `false` skips: an absent flag (a deep link,
      // an offline entry, a stale route-state after a republish, or a
      // continuation navigated from ContinueSeries, which never carries
      // this key at all) falls through to the fetch exactly as before D8,
      // because absence means "unknown", not "ineligible". Pure
      // optimization: the fetch this replaces already fails safe (any
      // failure resolves to null, which ReaderPage renders as the generic
      // story), so a stale eligibility hint can only ever cost or save one
      // avoidable round trip, never change what the child sees.
      // #VERIFY: ReaderRoute.test.tsx "ReaderRoute personalization
      // eligibility route state (D8)".
      if (personalizationEligible === false) return null
      // Fetch-authoritative with a cached fallback, NOT cache-first: both reads
      // start together (they are independent), but the network answer decides
      // the outcome whenever the server responds, and the cache is consulted
      // only when the fetch fails. That priority is deliberate: revocation must
      // win over freshness, so a cached name is never rendered past an
      // authoritative answer that withdrew it. The accepted cost is that with a
      // dead backend the story reads generic until the fetch fails (up to the
      // request timeout) before the cached name appears. The cache is what
      // still lets a downloaded book render a child's name with no network at
      // all; the reconcile is what makes a revocation land on the next
      // connection (offline/revocation.ts).
      //
      // The cache read degrades to undefined on its own failure: a broken
      // IndexedDB must not reject the whole fetcher and silently disable
      // personalization for an online reader whose network fetch would have
      // answered. (fetchValues never rejects; the adapter maps every failure
      // to null.)
      const [cached, fresh] = await Promise.all([
        getCachedPersonalizationValues(storybookId).catch((err: unknown) => {
          console.warn('personalization: cached values read failed; continuing without cache:', err)
          return undefined
        }),
        fetchValues(storybookId),
      ])
      if (fresh === null) {
        // No authoritative answer: keep rendering from cache for THIS read, and
        // leave the cache alone. reconcilePersonalizationValues treats null as
        // revocation, which is right when the server answered and wrong when it
        // never did, so it is deliberately not called here.
        return cached ?? null
      }
      try {
        await reconcilePersonalizationValues(storybookId, fresh)
      } catch (err) {
        // A failed revocation delete must be observable (the revoked payload is
        // still at rest), but must not change what the child sees: the fresh
        // answer still decides this render.
        console.warn('personalization: cache reconcile failed:', err)
      }
      return Object.keys(fresh.values).length === 0 ? null : fresh
    }
  }, [api, personalizationEligible])
  // Flag-off residue purge (ADR-023 rollout): a build with
  // VITE_FEATURE_PERSONALIZATION off must not leave previously cached values
  // payloads at rest until sign-out. With the flag off the fetcher above never
  // runs, so nothing else would ever touch the store; clear it on reader mount
  // instead. Fire-and-forget and idempotent (clearing an already-empty store is
  // a no-op), so running per mount rather than once per session is cheap and
  // cannot be starved by ordering. Warn on failure so a purge that cannot run
  // is observable; never log the values themselves.
  useEffect(() => {
    if (isPersonalizationEnabled()) return
    void clearPersonalizationValues().catch((err: unknown) => {
      console.warn('personalization: flag-off residue purge failed:', err)
    })
  }, [])
  const navigate = useNavigate()
  const continuation = useMemo(() => parseContinuation(location.state), [location.state])
  // K7 / Phase 4b read-aloud: this route only ever gets a profile id, never
  // the full ProfileView (and its tts_enabled flag), so it reads back the
  // value ProfilePickerPage cached at pick time rather than adding a second
  // /v1/profiles fetch on every reader page load. A profile ReaderRoute
  // knows nothing about (e.g. a deep link opened without going through the
  // picker) resolves to false, hiding the toggle rather than guessing.
  const ttsEnabled = useMemo(
    () => (profileId ? getReadAloudPreference(profileId) : false),
    [profileId]
  )

  const [replayFailedCount, setReplayFailedCount] = useState(0)
  const { showToast } = useToast()
  const handleReplayOutcome = useCallback(
    (o: ReplayOutcome) => {
      if (o.failed.length > 0) setReplayFailedCount(o.failed.length)
      // #ASSUME: data-integrity: newest-write-wins. A reconnect-replay conflict
      // (o.conflicts: the server row advanced under a queued offline write) is
      // resolved silently by discarding the held local writes and keeping the
      // server's newest state; the child is never shown a "which place do you
      // want to keep?" dialog. This can drop a queued local step by design (see
      // the same product decision in ReaderPage.tsx's live-save 409 path).
      // Those writes were already dequeued by replayQueue, so no local queue
      // state lingers. A genuine replay FAILURE (o.failed: a non-offline server
      // error) is different and still surfaces the ask-a-grown-up banner below.
      // #VERIFY: ReaderRoute.test.tsx "silently discards a replayed 409 without
      // showing a conflict dialog".
      //
      // A clean reconnect replay (queued progress reached the server with
      // nothing held back) still gets its positive confirmation; a conflict or
      // a failure suppresses the toast so it never contradicts a silent
      // discard or the failed banner.
      if (o.replayed > 0 && o.conflicts.length === 0 && o.failed.length === 0) {
        showToast('All caught up! Your reading is saved.', { tone: 'success' })
      }
    },
    [showToast]
  )
  useReplayOnReconnect(syncApi, handleReplayOutcome)

  const dismissReplayFailedBanner = useCallback(() => setReplayFailedCount(0), [])

  if (!profileId || !storybookId || !version) {
    return (
      <EmptyState
        title="We couldn't tell which story to open"
        description="This link is missing some information. Let's go back to the start."
        actions={
          <Button variant="ghost" onClick={() => void navigate(KID_PICKER_PATH)}>
            Back to start
          </Button>
        }
      />
    )
  }
  const parsedVersion = Number(version)
  if (!Number.isInteger(parsedVersion) || parsedVersion < 1) {
    return (
      <EmptyState
        title="That story link looks wrong"
        description="This story link isn't valid. Let's go back to your books."
        actions={<BackToLibrary profileId={profileId} />}
      />
    )
  }

  // #CRITICAL: security (SEC-F1): if a child session exists for a DIFFERENT
  // profile than the one in the URL, refuse to open this profile's story, even
  // from the offline cache (ReaderPage loads cache-first and never hits the
  // server when the blob is cached, so the online 401 gate alone would not stop
  // this). Without it a sibling on a shared device could deep-link to another
  // profile's reader and read their downloaded books and progress. A route with
  // no session at all is left to the online 401 + picker recovery.
  // #VERIFY: ReaderRoute.test.tsx "refuses a story for a mismatched profile".
  const activeSession = getValidChildSession()
  if (activeSession && activeSession.profileId !== profileId) {
    return (
      <EmptyState
        title="That's not your bookshelf"
        description="Ask a grown-up to help you get back to your own books."
        actions={
          <Button variant="ghost" onClick={() => void navigate(KID_PICKER_PATH)}>
            Back to start
          </Button>
        }
      />
    )
  }

  return (
    <>
      {/* Keyed by the route params so navigating to a different story (or a
          different version/profile) fully remounts ReaderPage instead of
          reusing the same instance; a stale in-flight load from the old story
          can then never resolve into the new one's state. */}
      <ReaderPage
        key={`${profileId}:${storybookId}:${parsedVersion}`}
        api={syncApi}
        fetchStory={fetchStory}
        fetchServerState={fetchServerState}
        recordCompletion={recordCompletion}
        fetchSeriesNext={fetchSeriesNext}
        continuation={continuation}
        profileId={profileId}
        storybookId={storybookId}
        version={parsedVersion}
        ttsEnabled={ttsEnabled}
        fetchReadingHistory={fetchReadingHistory}
        submitFlag={submitFlag}
        fetchPersonalizationValues={fetchPersonalizationValues}
      />
      {replayFailedCount > 0 && (
        <div role="alert" className="replay-failed-banner">
          <span>
            {"We couldn't save some of your reading. Ask a grown-up if this keeps happening."}
          </span>
          {/* "OK", not "Dismiss": young kids read this button too (same rule
              as the toast's OK in ToastProvider.tsx). */}
          <button
            type="button"
            className="replay-failed-banner__ok"
            onClick={dismissReplayFailedBanner}
          >
            OK
          </button>
        </div>
      )}
    </>
  )
}
