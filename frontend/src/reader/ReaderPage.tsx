/**
 * The reader page: loads a story (cache-first, then network), resumes saved
 * progress, plays it, persists each step, and reconciles multi-device conflicts.
 *
 * The engine owns no server revision (its ReadingState.state_revision is always
 * 0), so this page tracks the last known server revision and stamps each save
 * with it; that is what makes sequential saves and 409 detection work.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'

import { ForbiddenError, StoryNotFoundError, type CompletionRequest } from '../api/readerApi'
import { cacheStorybook, getCachedStorybook, getReadingState } from '../offline/db'
import {
  LocalWriteError,
  OfflineError,
  type SyncApi,
  resolveConflict,
  saveProgress,
} from '../offline/sync'
import type { ReadingState, Storybook } from '../player/types'
import { BackToLibrary } from './BackToLibrary'
import { ConflictDialog } from './ConflictDialog'
import { DownloadNeeded } from './DownloadNeeded'
import { Reader } from './Reader'

export interface ReaderPageProps {
  api: SyncApi
  fetchStory: (storybookId: string, version: number) => Promise<Storybook>
  profileId: string
  storybookId: string
  version: number
  deviceId?: string
  /** Records a completion when the reader reaches an ending. Defaults to a no-op. */
  recordCompletion?: (body: CompletionRequest) => Promise<void>
}

type ErrorPhase = 'not-found' | 'forbidden' | 'offline' | 'error'

// A discriminated union, not parallel phase/story/initialReading state: the
// 'reading' variant is the only one carrying a story, so phase === 'reading'
// guarantees story is present at the type level instead of relying on a
// defensive `phase === 'offline' || !story` check to paper over a desync.
// Each error phase gets its own member (not one `{ phase: ErrorPhase }`
// member): TypeScript can only narrow a member fully away via a sequence of
// separate `if (x.phase === '...') return` checks when every member's
// discriminant is a single literal, not a multi-value union.
type PageState =
  | { phase: 'loading' }
  | { phase: 'reading'; story: Storybook; initialReading: ReadingState | undefined }
  | { phase: 'not-found' }
  | { phase: 'forbidden' }
  | { phase: 'offline' }
  | { phase: 'error' }

interface ConflictState {
  local: ReadingState
  server: ReadingState
}

function loadErrorPhase(error: unknown): ErrorPhase {
  if (error instanceof StoryNotFoundError) return 'not-found'
  if (error instanceof ForbiddenError) return 'forbidden'
  if (error instanceof OfflineError) return 'offline'
  return 'error'
}

export function ReaderPage({
  api,
  fetchStory,
  profileId,
  storybookId,
  version,
  deviceId,
  recordCompletion = () => Promise.resolve(),
}: ReaderPageProps) {
  const [pageState, setPageState] = useState<PageState>({ phase: 'loading' })
  const [conflict, setConflict] = useState<ConflictState | null>(null)
  // A single-instance-lifetime warning, not tied to the load phase: a dropped
  // save doesn't stop the reader from playing, so it renders as a banner
  // alongside the reading UI rather than as its own page state.
  const [saveWarning, setSaveWarning] = useState<'lost' | 'failing' | null>(null)
  // Bumped to remount the Reader (and re-seed its machine) when we adopt the
  // server's state; the machine reads its input only at creation.
  const [readerKey, setReaderKey] = useState(0)
  const revisionRef = useRef(0)
  const failedSaveCountRef = useRef(0)
  // Content signature of the last save this instance issued. Guards against the
  // React StrictMode double-invoke firing two identical saves for the same state.
  const lastSaveSignatureRef = useRef<string | null>(null)
  // Guards a load() call against a later, fresher load() resolving first (e.g.
  // a double-clicked "Try again"). ReaderRoute also keys ReaderPage by story
  // identity so navigating to a different story remounts instead of reusing
  // this guard across stories.
  const loadGenerationRef = useRef(0)
  const navigate = useNavigate()

  const load = useCallback(async () => {
    const generation = ++loadGenerationRef.current
    const stale = () => loadGenerationRef.current !== generation

    // IndexedDB is a cache, not a dependency: a read failure here (private
    // browsing, blocked storage, eviction) degrades to a cache miss so the
    // network fetch below still gets a chance, instead of blocking the whole
    // story on local storage being available.
    let cached: Storybook | undefined
    try {
      cached = await getCachedStorybook(storybookId, version)
    } catch {
      cached = undefined
    }
    if (!cached) {
      try {
        cached = await fetchStory(storybookId, version)
      } catch (error) {
        if (!stale()) setPageState({ phase: loadErrorPhase(error) })
        return
      }
      try {
        await cacheStorybook(cached)
      } catch {
        // Best-effort: the story is already in hand from the network, so a
        // failure to cache it locally must not block reading it now.
      }
    }
    let saved: ReadingState | undefined
    try {
      saved = await getReadingState(profileId, storybookId)
    } catch {
      // Same as above: no local reading state available is not fatal, it
      // just means this session starts fresh instead of resuming.
      saved = undefined
    }
    if (stale()) return
    revisionRef.current = saved?.state_revision ?? 0
    setPageState({ phase: 'reading', story: cached, initialReading: saved })
  }, [fetchStory, profileId, storybookId, version])

  // Load on mount and whenever the load inputs change.
  useEffect(() => {
    void load()
  }, [load])

  const retry = useCallback(() => {
    setPageState({ phase: 'loading' })
    void load()
  }, [load])

  const persist = useCallback(
    async (reading: ReadingState) => {
      // #CRITICAL: timing: the app runs under <StrictMode> (main.tsx), so mount effects
      // double-invoke in dev and Reader's progress effect reports the initial state
      // twice. Each save mints a fresh event_id, so the server's event-id dedup misses
      // and its revision check 409s the second write, surfacing a false cross-device
      // conflict (issue #86).
      // #VERIFY: skip a save whose CONTENT matches the last one issued, computed and
      // stored synchronously before any await, so the second fire is a no-op and no
      // duplicate PUT (hence no 409) is sent. Content-only (not revision) so it also
      // dedupes when the first save has already advanced revisionRef.
      const signature = JSON.stringify({
        current_node: reading.current_node,
        var_state: reading.var_state,
        path: reading.path,
        visit_set: reading.visit_set,
      })
      // #EDGE: data-integrity: save_slots is excluded from the signature because the engine never mutates it today; if save slots become live, add them here or a slot-only change would be skipped as a duplicate.
      // #VERIFY: player/engine.ts save_slots handling before enabling slots.
      // #EDGE: data-integrity: JSON.stringify key order follows insertion order; two
      // distinct-but-equal states rebuilt with different key order would miss the dedup
      // (a harmless extra save), never falsely skip a real content change.
      if (lastSaveSignatureRef.current === signature) {
        return
      }
      lastSaveSignatureRef.current = signature
      const stamped: ReadingState = {
        ...reading,
        state_revision: revisionRef.current,
      }
      try {
        const result = await saveProgress(api, profileId, storybookId, stamped, {
          deviceId,
        })
        failedSaveCountRef.current = 0
        setSaveWarning(null)
        if (result.kind === 'saved') {
          revisionRef.current = result.row.state_revision
        } else if (result.kind === 'conflict') {
          setConflict({ local: stamped, server: result.currentRow })
        }
      } catch (error) {
        if (error instanceof LocalWriteError) {
          // #CRITICAL: data-integrity: this step is cached nowhere, not locally
          // and not on the server, and nothing else will ever retry it.
          // #VERIFY: surface it immediately (not only after repeats): unlike a
          // remote hiccup, a single occurrence here already means real loss.
          console.error('[reader] local progress write failed', {
            profileId,
            storybookId,
            revision: revisionRef.current,
            error,
          })
          setSaveWarning('lost')
          return
        }
        failedSaveCountRef.current += 1
        console.error('[reader] progress save failed', {
          profileId,
          storybookId,
          revision: revisionRef.current,
          attempt: failedSaveCountRef.current,
          error,
        })
        // #ASSUME: external-resources: a single dropped remote save is often a
        // transient network blip; only a repeated failure indicates a real,
        // ongoing problem worth interrupting the reader for.
        // #VERIFY: two consecutive failures is the threshold before surfacing.
        if (failedSaveCountRef.current >= 2) {
          setSaveWarning('failing')
        }
      }
    },
    [api, profileId, storybookId, deviceId]
  )

  // Stable handler so the Reader's progress effect does not re-fire (and re-save
  // unchanged state) on every ReaderPage re-render.
  const handleProgress = useCallback((reading: ReadingState) => void persist(reading), [persist])

  const handleComplete = useCallback(
    (endingId: string) => {
      // #EDGE: external-resources: completion recording is best-effort. A failed
      // post must never surface a raw error on the kid ending screen.
      // #VERIFY: swallow to console.error; the child still sees "The End".
      void recordCompletion({
        profile_id: profileId,
        storybook_id: storybookId,
        version,
        ending_id: endingId,
      }).catch((error: unknown) => {
        console.error('[reader] completion post failed', {
          profileId,
          storybookId,
          version,
          endingId,
          error,
        })
      })
    },
    [recordCompletion, profileId, storybookId, version]
  )

  const keepThisDevice = useCallback(async () => {
    if (!conflict) return
    const result = await resolveConflict(
      api,
      profileId,
      storybookId,
      conflict.local,
      conflict.server,
      'continue_from_this_device',
      { deviceId }
    )
    if (result.kind === 'saved') {
      revisionRef.current = result.row.state_revision
    }
    setConflict(null)
  }, [api, conflict, deviceId, profileId, storybookId])

  const adoptNewest = useCallback(async () => {
    if (!conflict) return
    await resolveConflict(
      api,
      profileId,
      storybookId,
      conflict.local,
      conflict.server,
      'use_newer_progress',
      { deviceId }
    )
    revisionRef.current = conflict.server.state_revision
    setPageState((prev) =>
      prev.phase === 'reading' ? { ...prev, initialReading: conflict.server } : prev
    )
    // Remount the Reader so its machine re-initialises from the adopted server
    // state; without this the reader keeps playing from the local position.
    setReaderKey((key) => key + 1)
    setConflict(null)
  }, [api, conflict, deviceId, profileId, storybookId])

  if (pageState.phase === 'loading') {
    return <p data-testid="loading">Loading...</p>
  }
  if (pageState.phase === 'not-found') {
    return (
      <EmptyState
        title="We couldn't find that story"
        description="This story isn't available. It may have been removed. Let's head back to your books."
        actions={<BackToLibrary profileId={profileId} />}
      />
    )
  }
  if (pageState.phase === 'forbidden') {
    return (
      <EmptyState
        title="You don't have access to this story"
        description="This story isn't available on this profile. Let's head back to your books."
        actions={<BackToLibrary profileId={profileId} />}
      />
    )
  }
  if (pageState.phase === 'error') {
    return (
      <EmptyState
        title="Something went wrong"
        description="We couldn't open this story right now. Please try again."
        actions={
          <>
            <Button variant="primary" onClick={retry}>
              Try again
            </Button>
            <BackToLibrary profileId={profileId} />
          </>
        }
      />
    )
  }
  if (pageState.phase === 'offline') {
    return (
      <DownloadNeeded
        onRetry={retry}
        onBackToLibrary={() => navigate(`/library/${profileId}`)}
      />
    )
  }
  const { story, initialReading } = pageState
  return (
    <>
      {saveWarning ? (
        <p role="alert" className="reader-save-warning" data-testid="save-warning">
          {saveWarning === 'lost'
            ? "We couldn't save that step. We'll keep trying."
            : "We're having trouble saving your progress. Keep reading; we'll keep trying."}
        </p>
      ) : null}
      <Reader
        key={readerKey}
        story={story}
        initialReading={initialReading}
        onProgress={handleProgress}
        onComplete={handleComplete}
        profileId={profileId}
      />
      {conflict ? (
        <ConflictDialog
          onKeepThisDevice={() => void keepThisDevice()}
          onUseNewest={() => void adoptNewest()}
        />
      ) : null}
    </>
  )
}
