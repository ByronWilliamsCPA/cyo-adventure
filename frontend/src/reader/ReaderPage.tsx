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

import {
  ForbiddenError,
  StoryNotFoundError,
  UnauthenticatedError,
  type CompletionRequest,
  type SeriesNextBookInfo,
} from '../api/readerApi'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import { cacheStorybook, getCachedStorybook, getReadingState, putReadingState } from '../offline/db'
import {
  LocalWriteError,
  OfflineError,
  type SyncApi,
  resolveConflict,
  saveProgress,
} from '../offline/sync'
import { Mascot } from '../kid/Mascot'
import { startContinuation } from '../player/engine'
import type { ContinuationSeed } from '../player/series'
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
  /** Cold-cache cross-device resume. Defaults to "no server state". */
  fetchServerState?: FetchServerState
  /** Records a completion when the reader reaches an ending. Defaults to a no-op. */
  recordCompletion?: RecordCompletion
  /** One-shot continuation seed for a fresh read (WS-G); ignored whenever any
   * saved progress exists (spec section 6 no-clobber rule). */
  continuation?: ContinuationSeed
  /** Forwarded to the Reader's ending screen. */
  fetchSeriesNext?: (profileId: string, storybookId: string) => Promise<SeriesNextBookInfo | null>
  /** The profile's `tts_enabled` flag (K7 / Phase 4b read-aloud), forwarded
   * straight to the Reader. See `ReaderRoute` for where this is resolved. */
  ttsEnabled?: boolean
}

type FetchServerState = (profileId: string, storybookId: string) => Promise<ReadingState | null>
type RecordCompletion = (body: CompletionRequest) => Promise<void>

// Stable module-level defaults, not inline default-parameter expressions: a
// default-parameter expression is re-evaluated to a fresh function reference
// on every render when the prop is omitted, which would change `load`'s
// identity every render (fetchServerState sits in its useCallback deps),
// re-firing the mount effect (`useEffect(() => void load(), [load])`) on
// every render and forming an unbounded reload loop (~650 GETs/500ms
// observed). A stable reference by identity is what keeps `load` stable.
const NO_SERVER_STATE: FetchServerState = () => Promise.resolve(null)
const NO_RECORD_COMPLETION: RecordCompletion = () => Promise.resolve()

type ErrorPhase = 'not-found' | 'forbidden' | 'unauthenticated' | 'offline' | 'error'

type SaveWarning = 'lost' | 'failing' | null

// How long a Leave tap waits for an in-flight save to settle before deciding
// whether to surface a loss. Bounded so a hung request can never trap a child
// in the reader.
const LEAVE_SAVE_WAIT_MS = 1500

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
  | { phase: 'unauthenticated' }
  | { phase: 'offline' }
  | { phase: 'error' }

interface ConflictState {
  local: ReadingState
  server: ReadingState
}

function loadErrorPhase(error: unknown): ErrorPhase {
  if (error instanceof StoryNotFoundError) return 'not-found'
  if (error instanceof ForbiddenError) return 'forbidden'
  if (error instanceof UnauthenticatedError) return 'unauthenticated'
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
  fetchServerState = NO_SERVER_STATE,
  recordCompletion = NO_RECORD_COMPLETION,
  continuation,
  fetchSeriesNext,
  ttsEnabled,
}: ReaderPageProps) {
  const [pageState, setPageState] = useState<PageState>({ phase: 'loading' })
  const [conflict, setConflict] = useState<ConflictState | null>(null)
  // A single-instance-lifetime warning, not tied to the load phase: a dropped
  // save doesn't stop the reader from playing, so it renders as a banner
  // alongside the reading UI rather than as its own page state.
  const [saveWarning, setSaveWarning] = useState<SaveWarning>(null)
  // Mirror of saveWarning for handlers that need the freshest value across an
  // await (state reads inside an async closure are frozen at render time).
  const saveWarningRef = useRef<SaveWarning>(null)
  // The latest in-flight persist() call. Leave awaits this (bounded) so a save
  // that is about to fail can surface its warning before the page unmounts.
  const pendingSaveRef = useRef<Promise<void> | null>(null)
  // Set once a Leave tap was blocked to show the lost-save warning; the next
  // tap then always navigates so a child can never be stuck in the reader.
  const leaveWarningShownRef = useRef(false)
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

  // Single write path for the save warning so the state (what renders) and the
  // ref (what async handlers read after an await) can never diverge.
  const updateSaveWarning = useCallback((warning: SaveWarning) => {
    saveWarningRef.current = warning
    setSaveWarning(warning)
  }, [])

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
    // Cold cache: fall back to the server's saved state for cross-device resume.
    // Local wins when present (it is the freshest); the server is consulted only
    // when local is absent.
    if (saved === undefined) {
      try {
        // #ASSUME: external-resources: the server may have no state (returns null)
        // or be unreachable (OfflineError); both mean "resume nothing", they must
        // not block a story the reader already holds.
        // #VERIFY: null and any thrown error both leave saved undefined -> fresh
        // start; the offline reading path is unchanged.
        const server = await fetchServerState(profileId, storybookId)
        // #CRITICAL: concurrency: a superseded load generation can still be
        // awaiting this fetch when a later generation resolves first and the
        // user keeps playing; persist() writes IndexedDB before the network,
        // so a stale generation's mirror write below could clobber a NEWER
        // local row with older server data.
        // #VERIFY: re-check stale() immediately after the await, before the
        // mirror write, and bail out entirely (no state update, no write)
        // when superseded.
        if (stale()) return
        if (server) {
          saved = server
          // Mirror into the local cache so the next open is cache-first. Best
          // effort: a mirror failure must not block resuming from the server row.
          try {
            await putReadingState(profileId, storybookId, server)
          } catch {
            // ignore: the in-memory `saved` still drives this session
          }
        }
      } catch {
        // offline or server error: start fresh; do not surface an error page.
        saved = undefined
      }
    }
    if (stale()) return
    revisionRef.current = saved?.state_revision ?? 0
    // #ASSUME: data-integrity: the continuation seed applies ONLY to a fresh
    // read (no local and no server state); any existing progress wins so a
    // re-continue can never clobber a child's place (WS-G spec section 6).
    // #VERIFY: ReaderPage.test.tsx "ignores a continuation when saved
    // progress exists".
    let initialReading = saved
    if (saved === undefined && continuation !== undefined) {
      try {
        initialReading = startContinuation(cached, continuation.entryNode, continuation.varState)
      } catch (error) {
        // Same failure mapping as the fetch above: a corrupt story blob (e.g.
        // a dangling start node) makes startContinuation throw, and an
        // unhandled throw here would leave the page stuck in Loading.
        if (!stale()) setPageState({ phase: loadErrorPhase(error) })
        return
      }
    }
    setPageState({ phase: 'reading', story: cached, initialReading })
  }, [fetchStory, fetchServerState, profileId, storybookId, version, continuation])

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
        updateSaveWarning(null)
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
          updateSaveWarning('lost')
          return
        }
        if (error instanceof UnauthenticatedError) {
          // #CRITICAL: security: the child session token is dead (expired or
          // revoked). Every subsequent save will 401 identically, so stop the
          // fire-on-every-choice retry loop here and drop any stale save
          // banner, then surface the ask-a-grown-up gate. Promising "we'll
          // keep trying" would be a lie: nothing retries until a grown-up
          // signs in again and a fresh session is minted.
          // #VERIFY: ReaderPage.test.tsx "shows the ask-a-grown-up gate and
          // stops saving when a save 401s".
          updateSaveWarning(null)
          setPageState({ phase: 'unauthenticated' })
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
          updateSaveWarning('failing')
        }
      }
    },
    [api, profileId, storybookId, deviceId, updateSaveWarning]
  )

  // Stable handler so the Reader's progress effect does not re-fire (and re-save
  // unchanged state) on every ReaderPage re-render. The in-flight promise is
  // kept in pendingSaveRef so handleLeave can settle it before unmounting;
  // persist() catches its own failures, so this promise never rejects.
  const handleProgress = useCallback(
    (reading: ReadingState) => {
      pendingSaveRef.current = persist(reading)
    },
    [persist]
  )

  // #CRITICAL: data-integrity: persist() is fired-and-forgotten on every
  // choice, and a failed local write's ONLY surfacing is the saveWarning
  // banner rendered inside this component. Navigating away on Leave unmounts
  // this page, so an in-flight save that fails after the tap would lose its
  // warning silently: the child's step is gone and nobody is told.
  // #VERIFY: covered by ReaderLeave.test.tsx: "surfaces a lost save and blocks
  // the first Leave tap; a second tap still leaves" and "navigates to the
  // library immediately when no save is pending or at risk".
  const handleLeave = useCallback(() => {
    void (async () => {
      // Second tap after the warning was surfaced: always leave. The banner
      // was shown; holding the child hostage to a failing save helps nobody.
      if (!leaveWarningShownRef.current) {
        const pending = pendingSaveRef.current
        if (pending) {
          // Bounded wait: give the in-flight save a chance to settle (and to
          // set the warning) without letting a hung request trap the reader.
          await Promise.race([
            pending,
            new Promise<void>((resolve) => setTimeout(resolve, LEAVE_SAVE_WAIT_MS)),
          ])
        }
        if (saveWarningRef.current === 'lost') {
          // The step is stored nowhere (see persist's LocalWriteError branch).
          // Stay on the page this tap so the role="alert" banner is actually
          // seen; the next tap leaves regardless.
          leaveWarningShownRef.current = true
          return
        }
      }
      void navigate(`/library/${profileId}`)
    })()
  }, [navigate, profileId])

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
    // Branded, kid-facing loading state (mirrors the library's role="status"
    // loading pattern); data-testid="loading" is pinned by ReaderPage tests.
    return (
      <div data-testid="loading" className="reader-loading" role="status" aria-live="polite">
        <Mascot size={96} className="reader-loading__mascot" />
        <p className="reader-loading__text">Opening your story...</p>
      </div>
    )
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
  if (pageState.phase === 'unauthenticated') {
    return (
      <EmptyState
        title="Ask a grown-up to help"
        description="A grown-up needs to sign in again before you can keep reading."
        actions={
          <>
            <Button variant="primary" onClick={() => void navigate(GUARDIAN_LOGIN_PATH)}>
              I am a grown-up
            </Button>
            <BackToLibrary profileId={profileId} />
          </>
        }
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
        onBackToLibrary={() => void navigate(`/library/${profileId}`)}
      />
    )
  }
  const { story, initialReading } = pageState
  return (
    <>
      {saveWarning ? (
        // Two honest variants, never shared copy: 'failing' is a transient
        // remote problem the next choice really does retry, so it may promise
        // "we'll keep trying". 'lost' is a permanent local-write failure (see
        // persist's LocalWriteError branch: the step is stored nowhere and
        // nothing will ever retry it), so promising a retry would be false.
        <p role="alert" className="reader-save-warning" data-testid="save-warning">
          {saveWarning === 'lost'
            ? "We couldn't save your last step. Your story will keep going, but that step might not be remembered. Ask a grown-up if this keeps happening."
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
        onLeave={handleLeave}
        fetchSeriesNext={fetchSeriesNext}
        ttsEnabled={ttsEnabled}
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
