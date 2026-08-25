/**
 * The reader page: loads a story (cache-first, then network), resumes saved
 * progress, plays it, persists each step, and reconciles multi-device conflicts.
 *
 * The engine owns no server revision (its ReadingState.state_revision is always
 * 0), so this page tracks the last known server revision and stamps each save
 * with it; that is what makes sequential saves and 409 detection work.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'

import {
  ForbiddenError,
  StoryNotFoundError,
  UnauthenticatedError,
  type CompletionOutcome,
  type CompletionRequest,
  type CompletionResult,
  type SeriesNextBookInfo,
  type SubmitFlagParams,
} from '../api/readerApi'
import type { KidFlagCreatedView, ReadingHistoryItem } from '../client/types.gen'
import { useApi } from '../hooks/useApi'
import { makeProgressApi, type EarnedBadgeCard } from '../kid/progressApi'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import {
  cacheStorybook,
  getCachedStorybook,
  getReadingState,
  isBadgeSeen,
  markBadgeSeen,
  putReadingState,
} from '../offline/db'
import { makeReadingTimeApi } from '../offline/readingTimeSync'
import {
  LocalWriteError,
  OfflineError,
  type SyncApi,
  resolveConflict,
  saveProgress,
} from '../offline/sync'
import { Mascot } from '../kid/Mascot'
import { startContinuation } from '../player/engine'
import type { ValuesPayload } from '../player/personalization'
import type { ContinuationSeed } from '../player/series'
import type { ReadingState, Storybook } from '../player/types'
import { BackToLibrary } from './BackToLibrary'
import {
  NO_CHARACTER_BINDING,
  deriveCharacterSeed,
  type CharacterBinding,
  type FetchActiveCharacterBinding,
} from './characterSeed'
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
  /**
   * Resolves the profile's active character (ADR-028) for a FRESH read, the
   * one case where no reading-state row exists yet to carry a server-
   * snapshotted seed. Defaults to "no active character", which reproduces
   * the pre-Task-9 behavior (open from the story's declared initials).
   * See `characterSeed.ts` for why the seed is consumed from the server
   * rather than derived here from the character's attributes.
   */
  fetchActiveCharacter?: FetchActiveCharacterBinding
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
  /** Forwarded straight to the Reader's ending screen (K6 endings tracker). */
  fetchReadingHistory?: (profileId: string) => Promise<ReadingHistoryItem[]>
  /** Forwarded straight to the Reader's chrome (K15 flag button). */
  submitFlag?: (params: SubmitFlagParams) => Promise<KidFlagCreatedView>
  /**
   * Resolves the ADR-023 values payload for this book. Omitted entirely when
   * `VITE_FEATURE_PERSONALIZATION` is off (see ReaderRoute), which is what makes
   * "no fetch, no resolver input" the structural default rather than a branch.
   */
  fetchPersonalizationValues?: (storybookId: string) => Promise<ValuesPayload | null>
  /**
   * The reading profile's `age_band` (ADR-026 decision 6), forwarded
   * straight to the Reader (see its own doc for the exact band list and the
   * "unknown means page-per-node" default). Resolved in `ReaderRoute` via a
   * best-effort profile lookup; omitted here has the identical effect as an
   * explicit `undefined`.
   */
  ageBand?: string
  /**
   * Reports to the server that this device now has this book cached offline
   * (G15 storage/download view). Takes only the storybook id: the caller
   * (`ReaderRoute`) closes over the device id and profile id, since neither
   * changes within one mounted reader. Best-effort, fire-and-forget from
   * this page's perspective (this prop returns void, not a Promise this
   * page would need to await or catch): a report failure must never block
   * or delay reading, which is already in hand from the IndexedDB cache
   * regardless of whether the server ever learns about it. Omitted entirely
   * (most existing tests, and any caller with no wiring for it) means
   * downloads are simply never reported, matching every other
   * optional-callback prop's own pattern.
   */
  reportDownload?: (storybookId: string) => void
  /**
   * Reports to the server that this device no longer has a book cached
   * offline (G15 storage/download view), the mirror image of
   * `reportDownload` above. Passed straight through to `cacheStorybook`'s
   * own `reportEviction` option (offline/db.ts) for the one eviction this
   * page can trigger: caching a newly-opened book that forces a
   * same-device, space-pressure eviction of a different one. Same contract
   * as `reportDownload`: fire-and-forget, best-effort, never awaited or
   * caught here, and never allowed to let a report failure touch the
   * eviction it describes. Omitted has the identical effect as
   * `reportDownload`'s own omission: the eviction still happens locally, it
   * is simply never reported.
   */
  reportRemoval?: (storybookId: string) => void
}

type FetchServerState = (profileId: string, storybookId: string) => Promise<ReadingState | null>
type RecordCompletion = (body: CompletionRequest) => Promise<CompletionResult>

// Stable module-level defaults, not inline default-parameter expressions: a
// default-parameter expression is re-evaluated to a fresh function reference
// on every render when the prop is omitted, which would change `load`'s
// identity every render (fetchServerState sits in its useCallback deps),
// re-firing the mount effect (`useEffect(() => void load(), [load])`) on
// every render and forming an unbounded reload loop (~650 GETs/500ms
// observed). A stable reference by identity is what keeps `load` stable.
const NO_SERVER_STATE: FetchServerState = () => Promise.resolve(null)
// Same stable-identity rule as NO_SERVER_STATE above: this sits in `load`'s
// useCallback deps, so an inline default-parameter expression would remint it
// every render and re-fire the mount effect in an unbounded reload loop.
const NO_ACTIVE_CHARACTER: FetchActiveCharacterBinding = () => Promise.resolve(null)
// #ASSUME: data-integrity: this default's resolved value is never actually
// rendered from: a caller that omits `recordCompletion` also has no reason
// to wire `fetchReadingHistory`/EndingsProgress, so the ending screen's
// tracker never mounts to read it. It exists only so handleComplete's
// `.then` has a well-typed value to flow through when the prop is omitted.
// #VERIFY: ReaderPage.test.tsx "does not reload in a loop when
// fetchServerState/recordCompletion are omitted".
const NO_RECORD_COMPLETION: RecordCompletion = () =>
  Promise.resolve({ is_new: false, found: 0, total: 0 })

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
  | {
      phase: 'reading'
      story: Storybook
      initialReading: ReadingState | undefined
      // Resolved during load(), not at render: a fresh read has to ASK the
      // server which character it is playing as (there is no row to read it
      // off), and render is not allowed to await. Holding the answer in the
      // same state member as the story keeps "which character" and "which
      // reading state" from ever being one render out of step.
      character: CharacterBinding
    }
  | { phase: 'not-found' }
  | { phase: 'forbidden' }
  | { phase: 'unauthenticated' }
  | { phase: 'offline' }
  | { phase: 'error' }

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
  fetchActiveCharacter = NO_ACTIVE_CHARACTER,
  recordCompletion = NO_RECORD_COMPLETION,
  continuation,
  fetchSeriesNext,
  ttsEnabled,
  fetchReadingHistory,
  submitFlag,
  fetchPersonalizationValues,
  ageBand,
  reportDownload,
  reportRemoval,
}: ReaderPageProps) {
  const [pageState, setPageState] = useState<PageState>({ phase: 'loading' })

  // W3.3/W3.2: this page builds its own network ports for reading-time
  // capture and progress off the shared axios instance, rather than adding
  // parameters ReaderRoute would have to thread through (this change's touch
  // scope does not extend to ReaderRoute.tsx). Both hand-typed (see each
  // module's own note on why): the routes landed the same day as this
  // change and the generated client has not been regenerated for their
  // exact wire shapes yet.
  const rawApi = useApi()
  const readingTimeApi = useMemo(() => makeReadingTimeApi(rawApi), [rawApi])
  const progressApi = useMemo(() => makeProgressApi(rawApi, profileId), [rawApi, profileId])

  // Guardian per-profile "pause time capture" toggle (W3.4), resolved
  // best-effort on mount. Starts false (capture on) so a slow or failing
  // settings fetch never silently stops a session's reading time from
  // accruing; it only ever turns capture OFF once the real setting is known.
  const [timeCapturePaused, setTimeCapturePaused] = useState(false)
  // Badge toasts follow the guardian's badges_enabled toggle (G19): off
  // suppresses the toast while awards still compute server-side, per the
  // gamification recommendation's controls table. Defaults true (show) and
  // only ever turns off once the real setting is known, mirroring the
  // capture toggle's fail-open-for-celebration posture above.
  const badgesEnabledRef = useRef(true)
  useEffect(() => {
    let cancelled = false
    progressApi
      .getProgress()
      .then((progress) => {
        if (!cancelled) {
          setTimeCapturePaused(progress.settings.time_capture_paused)
          badgesEnabledRef.current = progress.settings.badges_enabled
        }
      })
      .catch((error: unknown) => {
        // Best-effort: a failed settings fetch must never block reading;
        // capture simply stays on (the safe default -- see above).
        console.error('[reader] progress settings fetch failed', { profileId, error })
      })
    return () => {
      cancelled = true
    }
  }, [progressApi, profileId])

  // W3.2: badge-unlock toast state. `checkForNewBadge` (wired into
  // handleComplete below) is the sole writer; IndexedDB `badge_seen` is the
  // durable per-device dedupe so a badge earned on a DIFFERENT device (whose
  // "seen" state this device never wrote) can still toast here once, but
  // never toasts twice on this same device even across a remount.
  // #ASSUME: data-integrity: badge seen-state is intentionally per-device,
  // not synced (gamification recommendation section 5: "badge seen-state
  // lives client-side in IndexedDB, avoiding a table"), so a family reading
  // the same profile across two devices could see the same badge toast once
  // per device rather than exactly once ever. Accepted: a badge is a
  // celebration, not a scarce resource, and a repeat toast on a second
  // device is a much kinder failure mode than a missed one.
  // #VERIFY: ReaderPage.test.tsx badge-toast tests.
  const [newlyEarnedBadge, setNewlyEarnedBadge] = useState<EarnedBadgeCard | null>(null)
  const checkForNewBadge = useCallback(
    async (badgesBefore: Promise<Set<string>>) => {
      try {
        // Cheap early-out only: skips the fetch when the setting is already
        // known to be off. It is NOT the gate, because the ref defaults true
        // and is read before any await, so a child who reaches an ending
        // before the mount-time settings fetch resolves would pass it.
        if (!badgesEnabledRef.current) return
        const before = await badgesBefore
        // `fresh`: this read is ordered AFTER the completion POST, so it must
        // be a request of its own rather than one already in flight from a
        // mount effect (see ProgressReadOptions).
        const after = await progressApi.getProgress({ fresh: true })
        const candidate = after.badges.find((badge) => !before.has(badge.id))
        if (candidate === undefined) return
        // #CRITICAL: security: the authoritative gate, read from the response
        // we just awaited rather than from the pre-await ref. It must stay
        // ahead of markBadgeSeen: that write consumes the badge's one toast
        // on this device, so suppressing AFTER marking would silently burn a
        // celebration the guardian merely paused. G19 is a guardian control
        // over what their child sees, so failing open on an unresolved fetch
        // is not acceptable here even though the ring/capture paths above
        // deliberately fail open for accrual.
        // #VERIFY: ReaderPage.test.tsx "suppresses the badge toast when
        // badges_enabled turns false after the ending is reached".
        if (!after.settings.badges_enabled) {
          badgesEnabledRef.current = false
          return
        }
        if (await isBadgeSeen(profileId, candidate.id)) return
        await markBadgeSeen(profileId, candidate.id)
        setNewlyEarnedBadge(candidate)
      } catch (error) {
        // Best-effort, purely celebratory: a failed check just means no
        // toast this time, never an error surfaced to the child.
        console.error('[reader] badge check failed', { profileId, error })
      }
    },
    [progressApi, profileId]
  )

  // ADR-023 P6: resolved independently of the story load, so a slow or failing
  // values fetch can never delay or fail the story itself. Starts null (generic)
  // and upgrades once resolved, which is safe because the resolver is total and
  // a re-render with a payload simply replaces generic words with personalized
  // ones.
  const [personalization, setPersonalization] = useState<ValuesPayload | null>(null)
  useEffect(() => {
    if (fetchPersonalizationValues === undefined) return
    let cancelled = false
    void fetchPersonalizationValues(storybookId)
      .then((payload) => {
        if (!cancelled) setPersonalization(payload)
      })
      .catch(() => {
        // #ASSUME: data-integrity: swallowed on purpose. The adapter already
        // resolves null on every failure it knows about; this catch covers a
        // caller (a test, a future adapter) that rejects instead. Either way the
        // correct outcome is the generic story, never an error screen.
        // #VERIFY: ReaderPage.test.tsx "still renders the story when the values
        // fetch rejects".
        if (!cancelled) setPersonalization(null)
      })
    return () => {
      cancelled = true
    }
  }, [fetchPersonalizationValues, storybookId])
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
  // Serializes saves against each other. persist() stamps `state_revision`
  // from revisionRef, which only advances when a save RESPONSE lands, so two
  // saves started inside one round-trip would stamp the SAME revision and the
  // server would reject the second as a cross-device conflict. ADR-026 makes
  // exactly that the normal mount at bands 8-11 and up: the reader walks the
  // whole opening stop before the child touches anything, reporting one state
  // per node walked. Distinct from pendingSaveRef, which exists so Leave can
  // await a save; this one exists so saves cannot overlap in the first place.
  const saveChainRef = useRef<Promise<void>>(Promise.resolve())
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
    // Whether this book is genuinely in this device's local cache right now.
    // A cache HIT proves it; a cache MISS only becomes true if the write
    // below actually succeeds.
    let isCachedLocally = false
    try {
      cached = await getCachedStorybook(storybookId, version)
      isCachedLocally = cached !== undefined
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
        await cacheStorybook(cached, { reportEviction: reportRemoval })
        isCachedLocally = true
      } catch {
        // Best-effort: the story is already in hand from the network, so a
        // failure to cache it locally must not block reading it now. But it
        // is NOT actually cached, so reportDownload below must not claim it
        // is -- the guardian's downloads view would otherwise show a book as
        // available offline on a device where it demonstrably is not.
      }
    }
    // G15: report this device having the book cached, whether it was
    // already cached (an IndexedDB hit above) or just freshly cached, so a
    // repeat read of an already-downloaded book still advances the
    // guardian-visible "last confirmed" signal (offline_downloads.py's
    // upsert semantics). Fire-and-forget: reportDownload itself never
    // returns a Promise this page would await or catch.
    // #ASSUME: data-integrity: gated on the cache write having actually
    // succeeded. The guardian's Downloads view answers "which books are
    // saved for offline reading, and where"; reporting unconditionally would
    // answer it wrongly in exactly the cases the catch above exists for
    // (quota exceeded, private browsing, blocked storage), showing a book as
    // downloaded on a device that cannot open it offline.
    // #VERIFY: ReaderPage.test.tsx "does not report a download when caching
    // failed" and "reports a download once when caching the fetched story
    // succeeds".
    if (isCachedLocally) reportDownload?.(storybookId)
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
    // ADR-028 Task 9 / issue #460. Which surface answers "who is playing, and
    // with what numbers" depends entirely on whether a reading-state row
    // exists, and this is the one place that decides:
    //
    // - A resumed read (or one this session already continued into) HAS a
    //   state, so the server's own snapshot on that state is authoritative
    //   and `deriveCharacterSeed` reads it back.
    // - A genuinely fresh read has none, and the server does not create one
    //   until the first PUT, so there is no snapshot to read. Asking for the
    //   profile's active character is the only way to open the book from the
    //   bound character's numbers instead of the story's declared initials,
    //   which is issue #460's headline defect and the client-side half the
    //   backend's `#EDGE` marker on `put_reading_state`'s create path names.
    //
    // #CRITICAL: data-integrity: the fresh-read seed is only applied when
    // `initialReading` is undefined. A WS-G series continuation has already
    // built its own opening state from the previous book's carried variables,
    // and layering a character seed on top would invent a client-side merge
    // the server has no counterpart for; worse, feeding that seed to the
    // machine would make RESTART silently drop the series carry. The two
    // carries are deliberately not combined here.
    // #VERIFY: ReaderPage.test.tsx "does not seed a continuation read from
    // the active character" and "seeds a fresh read from the profile's active
    // character".
    let character = deriveCharacterSeed(initialReading)
    if (initialReading === undefined) {
      // Never rejects (the adapter maps every failure to null), but a caller
      // supplying its own port might; either way an unresolved character just
      // means an unseeded read, never an error screen.
      const active = await fetchActiveCharacter(profileId).catch(() => null)
      if (stale()) return
      character = active ?? NO_CHARACTER_BINDING
    }
    setPageState({ phase: 'reading', story: cached, initialReading, character })
  }, [
    fetchStory,
    fetchServerState,
    fetchActiveCharacter,
    profileId,
    storybookId,
    version,
    continuation,
    reportDownload,
    reportRemoval,
  ])

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
        // save_slots is now live (bookmarks, player/engine.ts's
        // saveBookmark/deleteBookmark/loadBookmark): included here so a
        // slot-only change (save or delete a bookmark with no other player
        // state change) is not skipped as a duplicate of the last save.
        save_slots: reading.save_slots,
      })
      // #EDGE: data-integrity: JSON.stringify key order follows insertion order; two
      // distinct-but-equal states rebuilt with different key order would miss the dedup
      // (a harmless extra save), never falsely skip a real content change.
      if (lastSaveSignatureRef.current === signature) {
        return
      }
      lastSaveSignatureRef.current = signature
      // #CRITICAL: concurrency: wait for any save already in flight before
      // reading revisionRef below. The chain slot is advanced SYNCHRONOUSLY,
      // before the first await, so a second persist() started in the same tick
      // queues behind this one instead of racing it and stamping a revision
      // this save is about to consume. See saveChainRef for the mechanism.
      // #VERIFY: ReaderPage.test.tsx "sends no self-conflicting save while
      // flowing the opening stop" drives the real two-emission ADR-026 mount
      // against a server double that enforces the revision precondition; the
      // suite-wide okApi() accepts every revision and cannot see this.
      const previousSave = saveChainRef.current
      let markSaveDone: () => void = () => {}
      saveChainRef.current = new Promise<void>((resolve) => {
        markSaveDone = resolve
      })
      await previousSave
      try {
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
            // #ASSUME: data-integrity: newest-write-wins. A 409 means another
            // device advanced this story's row; we silently adopt the server's
            // current row (the most recent write) and keep reading. This can
            // discard THIS device's local position even when the other device is
            // LESS far along, moving the child to wherever that device last was.
            // That data loss is deliberate, per the product decision: a 5-10 year
            // old cannot reason about a "which place do you want to keep?" prompt,
            // so reading must never block on a conflict and no dialog is ever
            // shown to the child. Reuses resolveConflict's use_newer_progress
            // branch (mirror the server row locally, then remount the Reader).
            // #VERIFY: ReaderPage.test.tsx "silently adopts the server position on
            // a 409 without showing a dialog"; e2e reader-conflict.spec.ts asserts
            // no conflict dialog ever appears.
            const serverRow = result.currentRow
            await resolveConflict(
              api,
              profileId,
              storybookId,
              stamped,
              serverRow,
              'use_newer_progress',
              { deviceId }
            )
            revisionRef.current = serverRow.state_revision
            // The adopted row is the server's own View, so it carries the
            // binding this read was actually recorded against; re-derive from it
            // rather than keeping the pre-conflict binding. (Before the binding
            // moved into page state it was recomputed at every render, so
            // omitting this here would be a silent regression: the chrome could
            // name one character while the machine replayed another's seed.)
            setPageState((prev) =>
              prev.phase === 'reading'
                ? { ...prev, initialReading: serverRow, character: deriveCharacterSeed(serverRow) }
                : prev
            )
            // Remount the Reader so its machine re-initialises from the adopted
            // server state; without this the reader keeps playing the local place.
            setReaderKey((key) => key + 1)
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
      } finally {
        // Always release the chain: the branches above return early on a lost
        // local write and on a dead session, and a slot never resolved would
        // wedge every later save behind it.
        markSaveDone()
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

  // W0.3 (design review 2026-08-01 section 3.4): the completion POST's own
  // response carries {is_new, found, total}, so EndingsProgress can render
  // the ending-screen tracker from it directly instead of racing a second
  // GET. 'pending' is the state while the POST is in flight; the ending
  // screen shows nothing rather than fetching (which would risk the same
  // under-report race this replaces).
  const [completionOutcome, setCompletionOutcome] = useState<CompletionOutcome>({
    status: 'pending',
  })

  const handleComplete = useCallback(
    (endingId: string) => {
      // #ASSUME: timing dependencies: reset to 'pending' the instant a new
      // ending is reached, before this call's POST settles, so
      // EndingsProgress can never show a stale PREVIOUS ending's outcome (or
      // prematurely fall back to fetching) while this ending's completion is
      // still in flight. RESTART re-reaching an earlier ending, or reaching a
      // second distinct ending later in the same session, are both covered:
      // Reader.tsx's completedEndingsRef gates onComplete to at-most-once per
      // distinct ending, but each of those calls still resets this state.
      // #VERIFY: ReaderPage.test.tsx "resets the completion outcome to
      // pending for each newly reached ending".
      setCompletionOutcome({ status: 'pending' })
      // W3.2: snapshot the badge set BEFORE this completion's POST, so the
      // toast can diff "what's new" rather than guessing from a single
      // post-completion read (which cannot distinguish a badge earned by
      // THIS completion from one earned earlier that this device simply
      // never toasted). Started in parallel with the completion POST, not
      // awaited here, so it never delays the ending-screen tracker.
      // `fresh` here too, and for a blunter reason than the "after" read: a
      // mount-time fetch that is still hanging would otherwise BE this
      // snapshot, so the diff would wait on it instead of on the completion.
      const badgesBefore = progressApi
        .getProgress({ fresh: true })
        .then((progress) => new Set(progress.badges.map((badge) => badge.id)))
        .catch(() => new Set<string>())
      void recordCompletion({
        profile_id: profileId,
        storybook_id: storybookId,
        version,
        ending_id: endingId,
      })
        .then((result) => {
          setCompletionOutcome({ status: 'ready', result })
          void checkForNewBadge(badgesBefore)
        })
        .catch((error: unknown) => {
          // #EDGE: external-resources: completion recording is best-effort. A
          // failed post must never surface a raw error on the kid ending
          // screen; it also leaves no {is_new, found, total} to render
          // directly, so EndingsProgress falls back to its own
          // fetchReadingHistory lookup (see its #ASSUME) instead of showing
          // nothing forever.
          // #VERIFY: swallow to console.error; the child still sees "The
          // End"; ReaderPage.test.tsx "falls back to unavailable when the
          // completion POST rejects".
          console.error('[reader] completion post failed', {
            profileId,
            storybookId,
            version,
            endingId,
            error,
          })
          setCompletionOutcome({ status: 'unavailable' })
        })
    },
    [recordCompletion, profileId, storybookId, version, progressApi, checkForNewBadge]
  )

  if (pageState.phase === 'loading') {
    // Branded, kid-facing loading state (mirrors the library's role="status"
    // loading pattern); data-testid="loading" is pinned by ReaderPage tests.
    return (
      <div data-testid="loading" className="reader-loading" role="status" aria-live="polite">
        <Mascot size={96} className="reader-loading__mascot" />
        <p className="reader-loading__text">Opening your story…</p>
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
  const { story, initialReading, character } = pageState
  const { characterName, seed } = character
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
        characterName={characterName}
        // Both seeds are forwarded unconditionally, unlike `initialReading`
        // above: either is ignored for the initial state whenever saved
        // progress exists, but each is a fact about how this read began, so a
        // restart must honour it either way (issue #460). They are never both
        // set for one read; see the #CRITICAL fresh-read note above.
        seed={seed}
        continuation={continuation}
        onProgress={handleProgress}
        onComplete={handleComplete}
        profileId={profileId}
        onLeave={handleLeave}
        fetchSeriesNext={fetchSeriesNext}
        ttsEnabled={ttsEnabled}
        fetchReadingHistory={fetchReadingHistory}
        completionOutcome={completionOutcome}
        submitFlag={submitFlag}
        personalization={personalization}
        ageBand={ageBand}
        readingTimeApi={readingTimeApi}
        timeCapturePaused={timeCapturePaused}
        progressApi={progressApi}
        newlyEarnedBadge={newlyEarnedBadge}
        onDismissBadgeToast={() => setNewlyEarnedBadge(null)}
      />
    </>
  )
}
