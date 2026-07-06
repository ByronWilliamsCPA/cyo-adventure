import { useCallback, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { Button } from '@ds/components/Button'
import {
  makeFetchServerState,
  makeFetchStory,
  makeRecordCompletion,
  makeSyncApi,
} from '../api/readerApi'
import { useApi } from '../hooks/useApi'
import { useReplayOnReconnect } from '../hooks/useReplayOnReconnect'
import type { QueuedWrite } from '../offline/db'
import { resolveConflict, saveProgress, type ReplayOutcome } from '../offline/sync'
import { KID_PICKER_PATH } from '../routes'
import { BackToLibrary } from './BackToLibrary'
import { ConflictDialog } from './ConflictDialog'
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
  const navigate = useNavigate()

  const [replayConflicts, setReplayConflicts] = useState<QueuedWrite[]>([])
  const [replayFailedCount, setReplayFailedCount] = useState(0)
  const handleReplayOutcome = useCallback((o: ReplayOutcome) => {
    if (o.conflicts.length > 0) setReplayConflicts(o.conflicts)
    if (o.failed.length > 0) setReplayFailedCount(o.failed.length)
  }, [])
  useReplayOnReconnect(syncApi, handleReplayOutcome)

  // #CRITICAL: concurrency: resolveKeepThisDevice resends each story's furthest
  // queued write after a B1 replay conflict. A held conflict entry never
  // reached the server, so this first resend carries the local device's own
  // state as-is; that resend can itself conflict again (a fresh concurrent
  // edit landed while the dialog was open), and this time saveProgress's
  // SaveResult carries a real currentRow to rebase onto. The resolution below
  // rebases and retries exactly once via resolveConflict's
  // 'continue_from_this_device' branch (offline/sync.ts); if that retry
  // conflicts too, the story's items are kept in replayConflicts so the
  // dialog re-surfaces for that story alone instead of the result being
  // silently discarded (the queued writes were already dequeued by B1, so a
  // dropped result is unrecoverable progress loss). replayConflicts is
  // cleared per-story from actual outcomes, never blanket-cleared, so an
  // unrelated story's still-open conflict is never wiped out by another
  // story's resolution. A thrown LocalWriteError or propagated HTTP error is
  // caught per story and routed to the existing failed-count banner instead
  // of escaping this onClick as an unhandled rejection.
  // #VERIFY: ReaderRoute.test.tsx "replay reconciliation (B2)" describe block
  // covers (a) resend conflict then retry succeeds (dialog closes, rebased
  // PUT sent), (b) resend re-conflicts after the retry (dialog stays open for
  // that story only), (c) resend throws (failed banner count increments, no
  // unhandled rejection escapes resolveKeepThisDevice).
  const resolveKeepThisDevice = useCallback(async () => {
    // Adopt the furthest (last) queued write per story; earlier writes for a
    // conflicted story were already superseded by this one (B1 semantics).
    const furthest = new Map<string, QueuedWrite>()
    for (const item of replayConflicts) {
      furthest.set(`${item.profile_id} ${item.storybook_id}`, item)
    }
    const stillConflicted: QueuedWrite[] = []
    let newFailures = 0
    for (const item of furthest.values()) {
      try {
        const result = await saveProgress(syncApi, item.profile_id, item.storybook_id, item.state)
        if (result.kind === 'conflict') {
          const retry = await resolveConflict(
            syncApi,
            item.profile_id,
            item.storybook_id,
            item.state,
            result.currentRow,
            'continue_from_this_device'
          )
          if (retry.kind === 'conflict') {
            stillConflicted.push(item)
          }
        }
      } catch {
        // Resend failed outright (LocalWriteError or a propagated HTTP
        // error): route it to the existing failed-progress banner instead of
        // re-throwing into this onClick as an unhandled rejection. Mirrors
        // replayQueue's non-offline-failure handling in offline/sync.ts.
        newFailures += 1
      }
    }
    setReplayConflicts(stillConflicted)
    if (newFailures > 0) {
      setReplayFailedCount((count) => count + newFailures)
    }
  }, [replayConflicts, syncApi])
  const resolveUseNewest = useCallback(() => setReplayConflicts([]), [])
  const dismissReplayFailedBanner = useCallback(() => setReplayFailedCount(0), [])

  if (!profileId || !storybookId || !version) {
    return (
      <EmptyState
        title="We couldn't tell which story to open"
        description="This link is missing some information. Let's go back to the start."
        actions={
          <Button variant="ghost" onClick={() => navigate(KID_PICKER_PATH)}>
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
        profileId={profileId}
        storybookId={storybookId}
        version={parsedVersion}
      />
      {replayConflicts.length > 0 && (
        <ConflictDialog onKeepThisDevice={resolveKeepThisDevice} onUseNewest={resolveUseNewest} />
      )}
      {replayFailedCount > 0 && (
        <div role="alert" className="replay-failed-banner">
          <span>Some offline progress could not be saved.</span>
          <button type="button" onClick={dismissReplayFailedBanner} aria-label="Dismiss">
            Dismiss
          </button>
        </div>
      )}
    </>
  )
}
