import { useCallback, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

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
import { useApi } from '../hooks/useApi'
import { useReplayOnReconnect } from '../hooks/useReplayOnReconnect'
import { getReadAloudPreference } from '../kid/readAloudPreference'
import { useToast } from '../notifications/useToast'
import { type ReplayOutcome } from '../offline/sync'
import { parseContinuation } from '../player/series'
import { KID_PICKER_PATH } from '../routes'
import { BackToLibrary } from './BackToLibrary'
import { ReaderPage } from './ReaderPage'

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
  const navigate = useNavigate()
  const location = useLocation()
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
