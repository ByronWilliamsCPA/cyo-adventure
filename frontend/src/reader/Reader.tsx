/**
 * The story reader UI.
 *
 * Drives the XState reader machine and renders the current passage with only the
 * visible choices (a false-condition choice is hidden, not disabled, per the
 * runtime semantics). On an ending node it shows the ending screen. Composes the
 * design-system components (PassageText, ChoiceButton) and a persistent top bar.
 */

import { useEffect, useMemo, useRef, type CSSProperties } from 'react'
import { useNavigate } from 'react-router'

import { Button } from '@ds/components/Button'
import { ChoiceButton } from '@ds/components/ChoiceButton'
import { PassageText } from '@ds/components/PassageText'
import { useMachine } from '@xstate/react'

import type { CompletionOutcome, SeriesNextBookInfo, SubmitFlagParams } from '../api/readerApi'
import type { KidFlagCreatedView, ReadingHistoryItem } from '../client/types.gen'
import type { EarnedBadgeCard, ProgressApi } from '../kid/progressApi'
import { canGoBack, currentEndingId, visibleChoices } from '../player/engine'
import { Mascot } from '../kid/Mascot'
import { readerMachine } from '../player/machine'
import {
  resolvePersonalization,
  stripSentinels,
  type ValuesPayload,
} from '../player/personalization'
import { SATISFYING_ENDING_KINDS, seriesMeta } from '../player/series'
import { canGoBackOneStop } from '../player/stops'
import type { ReadingState, Storybook, VarState } from '../player/types'
import type { ReadingTimeApi } from '../offline/readingTimeSync'
import { BackToLibrary } from './BackToLibrary'
import { BadgeUnlockToast } from './BadgeUnlockToast'
import { ContinueSeries } from './ContinueSeries'
import { DedicationOverlay } from './DedicationOverlay'
import { EndingsGalleryButton } from './EndingsGalleryButton'
import { EndingsProgress } from './EndingsProgress'
import { FlagButton } from './FlagButton'
import { ReaderChrome } from './ReaderChrome'
import { TextSizeControl } from './TextSizeControl'
import { useReaderFontScale } from './useReaderFontScale'
import { useReadingTimeAccumulator } from './useReadingTimeAccumulator'
import { isFlowedBand, readerPositionLabel } from './readerProgress'
import { useFlowedStop } from './useFlowedStop'
import { useReadAloud } from './useReadAloud'
import './reader.css'

export interface ReaderProps {
  story: Storybook
  initialReading?: ReadingState
  onProgress?: (reading: ReadingState) => void
  /** Called once with the ending id when the reader reaches an ending. */
  onComplete?: (endingId: string) => void
  /** Profile whose library the ending screen's "Back to my books" returns to. */
  profileId: string
  /**
   * Optional handler for the always-visible Leave button. When provided it
   * replaces the default navigation so the owner (ReaderPage) can settle an
   * in-flight progress save before leaving; when omitted, Leave navigates
   * straight to the profile's library as before.
   */
  onLeave?: () => void
  /** Resolves the next readable series book; when provided, a satisfying
   * ending of a non-final series book offers "Continue the series". */
  fetchSeriesNext?: (profileId: string, storybookId: string) => Promise<SeriesNextBookInfo | null>
  /**
   * The profile's `tts_enabled` flag (K7 / Phase 4b read-aloud), threaded in
   * from `ReaderRoute` via `readAloudPreference.ts`. Defaults to false so a
   * profile ReaderRoute knows nothing about (or a caller that omits this
   * prop, e.g. most existing tests) never shows the toggle. Browser support
   * is checked separately (`useReadAloud`); both must hold for the toggle to
   * render.
   */
  ttsEnabled?: boolean
  /** Resolves the profile's endings-tracker data (K6); when provided, the
   * ending screen shows "You found ending N of M" once total_endings > 1.
   * Omitted entirely (no fetch attempted) when the caller has none to offer. */
  fetchReadingHistory?: (profileId: string) => Promise<ReadingHistoryItem[]>
  /** The just-reached ending's POST /completions outcome (W0.3), forwarded
   * to EndingsProgress so the ending screen can render the tracker directly
   * from the completion response (and distinguish a new find from a repeat
   * visit) instead of always racing fetchReadingHistory. Omitted entirely
   * by a caller with no POST-outcome tracking, which keeps the
   * fetchReadingHistory-only behavior. */
  completionOutcome?: CompletionOutcome
  /** Submits a child's structured content flag (K15). When provided, the
   * chrome offers a "Tell a grown-up" affordance; FlagButton itself hides
   * when no valid child session exists for this profile, so omitting this
   * prop (e.g. a caller with no wiring for it) is not the only way the
   * affordance can be absent. */
  submitFlag?: (params: SubmitFlagParams) => Promise<KidFlagCreatedView>
  /**
   * The resolved ADR-023 values payload, or null/absent for the generic story.
   * Resolved into the passage, the ending title, and the read-aloud text, and
   * nowhere else: admin review surfaces show markers on purpose (ADR-023
   * section 10). Choice labels never legally carry sentinels
   * (generation/binding.py) so they are never RESOLVED, but they do get a
   * defensive strip to generic words at render, because a defensive strip is
   * cheaper than trusting every future write path.
   */
  personalization?: ValuesPayload | null
  /**
   * The reading profile's `age_band` (ADR-026 decision 6: band is the source
   * of truth for stop-flowed vs. one-node-per-page rendering), threaded in
   * from ReaderRoute via a best-effort profile lookup. `undefined` (the
   * lookup is in flight, has failed, or the caller has none to offer, e.g.
   * most existing tests) renders the pre-ADR-026 one-node-per-page behavior,
   * matching every band this ADR does not name (3-5, 5-8) -- an unknown band
   * is never treated as flowed. See `readerProgress.ts`'s `isFlowedBand` for
   * the exact band list.
   */
  ageBand?: string
  /**
   * The reading-time flush port (W3.3), forwarded straight to the
   * accumulator hook. Omitted entirely (e.g. most existing tests) means the
   * hook still accrues into IndexedDB locally but never attempts a network
   * flush; see `useReadingTimeAccumulator`'s own doc.
   */
  readingTimeApi?: ReadingTimeApi
  /** Guardian per-profile "pause time capture" toggle (resolved gamification
   * settings). Defaults to false (capture on) so a caller with no settings
   * fetch wired yet (most existing tests) behaves as before. */
  timeCapturePaused?: boolean
  /**
   * The progress port (W3.2), forwarded to the ending screen's Endings
   * Gallery entry. Omitted entirely means the "See your endings" button
   * does not render (mirrors `fetchReadingHistory`'s own optional pattern).
   */
  progressApi?: ProgressApi
  /** A newly-earned badge to toast on the ending screen (W3.2), or null/
   * undefined for none. The caller (ReaderPage) owns the pre/post progress
   * comparison and the IndexedDB "seen" bookkeeping; this component only
   * renders whatever it is handed. */
  newlyEarnedBadge?: EarnedBadgeCard | null
  /** Dismisses the badge-unlock toast (marks it seen on the caller's side). */
  onDismissBadgeToast?: () => void
  /**
   * The name of the persistent character (ADR-028) this reading state's
   * `seed` was snapshotted from by the server, or null/undefined when no
   * character is bound to this read. Forwarded straight to ReaderChrome,
   * which renders it when present and renders nothing (no placeholder) when
   * it is null or undefined; see ReaderPage's `deriveCharacterSeed` for why
   * this always names the character the SEED came from, not whichever
   * character happens to be active on the profile right now.
   */
  characterName?: string | null
  /**
   * The bound character's carried attributes (Task 5/6, ADR-028), threaded
   * straight into the reader machine's input so RESTART and Go back
   * (machine.ts's `reset`/`applyBack`, both keyed on `context.seed`)
   * re-derive the same seeded start this read began with, instead of the
   * story's declared initials (issue #460). `undefined` means "no character
   * bound"; the caller (ReaderPage's `deriveCharacterSeed`) is responsible
   * for converting a JSON `null` (no character) to `undefined` before it
   * reaches this prop, since `ReaderInput.seed` is typed `VarState |
   * undefined`, never `| null`.
   *
   * #ASSUME: data-integrity: this prop is already `undefined` (not `null`)
   * when no character is bound, because the only production caller routes
   * every value through `characterSeed.ts::deriveCharacterSeed`, which does
   * the `?? undefined` conversion once at the boundary. A `null` arriving
   * here would type-check nowhere but would, if forced through, flip
   * `safeStart`'s `seed === undefined` branch and silently change which of
   * `start()`/`startContinuation()` every RESTART and Go back calls.
   * #VERIFY: ReaderPage.test.tsx "converts a null seed_var_state to
   * undefined at the boundary" pins the conversion; ReaderPage.test.tsx
   * "carries the character seed through RESTART inside the reader" pins the
   * rendered consequence of a seed that does arrive.
   */
  seed?: VarState
}

export function Reader({
  story,
  initialReading,
  onProgress,
  onComplete,
  profileId,
  onLeave,
  fetchSeriesNext,
  ttsEnabled = false,
  fetchReadingHistory,
  completionOutcome,
  submitFlag,
  personalization = null,
  ageBand,
  readingTimeApi,
  timeCapturePaused = false,
  progressApi,
  newlyEarnedBadge,
  onDismissBadgeToast,
  characterName = null,
  seed,
}: ReaderProps) {
  const navigate = useNavigate()
  const fontScale = useReaderFontScale(profileId)
  const [snapshot, send] = useMachine(readerMachine, {
    input: { story, reading: initialReading, seed },
  })
  const { reading, error: choiceError } = snapshot.context
  const node = story.nodes.find((n) => n.id === reading.current_node)

  // ADR-026 (W1.1): 8-11 and up flow consecutive single-choice, non-ending
  // nodes into one rendered stop; 3-5/5-8 keep today's one-node-per-page
  // rendering. `flowed` gates every piece of stop-specific behavior below so
  // an unrecognized/missing band (most existing tests, a caller with no
  // profile lookup yet) is always the pre-ADR-026 path.
  const flowed = isFlowedBand(ageBand)
  // See useFlowedStop.ts: this hook is the only thing that silently walks
  // the machine through a flowed run's intermediate nodes (via the same
  // public CHOOSE event a tap would send), so a rendered stop's effects and
  // visit_set entries are applied for real, not just displayed.
  const { stop: flowedStop, originReading } = useFlowedStop(story, reading, send, flowed)
  const nodesById = useMemo(() => new Map(story.nodes.map((n) => [n.id, n])), [story])

  // #CRITICAL: security: resolved here rather than at each JSX site so no future
  // render branch can add a fourth path that shows a raw marker to a child.
  // ADR-023 section 10: a sentinel on a kid-facing surface is a straightforward
  // visual defect and must never appear, and that is true whether or not the
  // family opted in, because `resolvePersonalization(text, null)` strips markers
  // to their generic words rather than passing them through.
  // Memoized on the input text and the payload: read-aloud word highlighting
  // re-renders this component per spoken word, and the resolve (two regex
  // passes over the passage) should not re-run on each of those renders.
  // A flowed stop joins each node's own resolved body with a blank line;
  // PassageText already renders a blank-line-separated string as one
  // paragraph per node (splitParagraphsWithOffsets), so this reuses that
  // component unchanged and keeps its global highlight-range-to-paragraph
  // mapping correct for read-aloud below. A length-1 stop (the common case,
  // and always true at an ending) reduces to exactly the single-node text
  // the pre-W1.1 reader rendered, so this replaces (not branches around) the
  // old `node?.body` computation.
  // #VERIFY: Reader.test.tsx "renders the generic word when there is no payload".
  const bodyText = useMemo(() => {
    if (flowedStop) {
      return flowedStop.nodeIds
        .map((id) => resolvePersonalization(nodesById.get(id)?.body ?? '', personalization))
        .join('\n\n')
    }
    return resolvePersonalization(node?.body ?? '', personalization)
  }, [flowedStop, nodesById, node, personalization])
  const endingTitle = useMemo(
    () => resolvePersonalization(node?.ending?.title ?? '', personalization),
    [node, personalization]
  )
  // The generic-resolved body, for the read-aloud egress guard: a non-local
  // TTS voice must never receive the personalized text (see useReadAloud).
  // Read-aloud must read the WHOLE flowed passage, not just its first node
  // (W1.1): joining every stop node's generic body the same way bodyText
  // does above is what makes that so, since useReadAloud is handed this
  // exact string.
  const genericBodyText = useMemo(() => {
    if (flowedStop) {
      return flowedStop.nodeIds
        .map((id) => resolvePersonalization(nodesById.get(id)?.body ?? '', null))
        .join('\n\n')
    }
    return resolvePersonalization(node?.body ?? '', null)
  }, [flowedStop, nodesById, node])

  // The dedication belongs on the opening screen: it is a note from a grown-up
  // on page one, and one repeated mid-story stops being a dedication.
  // `path.length <= 1` plus the start-node check covers every page-one state:
  // a fresh read, RESTART (a fresh single-entry path), and a post-back return
  // to the start node, which is BY DESIGN indistinguishable from a short read,
  // because the engine's back() truncates the recorded path; backing up to
  // page one therefore legitimately re-shows the dedication.
  // #ASSUME: timing dependencies: at a flowed band, `reading` (the machine's
  // live state) can already be silently advanced past the start node by the
  // time this renders (useFlowedStop's layout effect runs before paint), so
  // checking the live state here would miss page one entirely. `originReading`
  // is the pre-advance state the currently-displayed stop was actually
  // composed from, so it is what page bands' `reading` already was.
  // #VERIFY: Reader.test.tsx "still shows the dedication overlay on page one
  // at a flowed band whose start node flows into a branch".
  const openingCheckState = flowed && originReading ? originReading : reading
  const atOpening =
    openingCheckState.path.length <= 1 && openingCheckState.current_node === story.start_node

  // Read-aloud (K7): the toggle itself renders in ReaderChrome, but the
  // speech content (passage body, then choice labels) is only known here.
  const readAloud = useReadAloud(ttsEnabled)

  // Active reading-time accumulation (W3.3): shared across all three render
  // branches below (error/ended/normal), each of which mounts its own
  // `.reader-shell` root -- only one branch renders at a time, so one ref
  // reattaching across them is correct, not a bug. Passive pointerdown/
  // keydown/scroll listeners on the shell (attached inside the hook) plus
  // the explicit recordInteraction() calls on choose()/go-back below cover
  // every interaction the recommendation names; read-aloud playing counts
  // via `isReadAloudPlaying` with no tap required.
  const shellRef = useRef<HTMLDivElement>(null)
  const { recordInteraction } = useReadingTimeAccumulator({
    profileId,
    api: readingTimeApi,
    paused: timeCapturePaused,
    isReadAloudPlaying: readAloud.speaking,
    containerRef: shellRef,
  })
  // Choice labels never legally carry sentinels (generation/binding.py), but
  // the module's own rationale applies here too: a defensive strip to generic
  // words is cheaper than trusting every future write path, and a label is a
  // kid-facing surface like any other. Strip only, never resolve: a personal
  // value in a label would be a new egress surface, not a feature.
  // At a flowed band the choices to render are the composed stop's TERMINAL
  // node's (ADR-026 decision 1), which is `flowedStop.state` -- by the time a
  // render actually paints this equals the live `reading` too (useFlowedStop
  // has already walked the machine there), but reading from the stop is
  // still correct during the one internal, never-painted render pass before
  // that walk completes.
  const choiceState = flowedStop?.state ?? reading
  const choices = useMemo(
    () =>
      visibleChoices(story, choiceState).map((choice) => ({
        ...choice,
        label: stripSentinels(choice.label),
      })),
    [story, choiceState]
  )

  // Report progress whenever the reading state changes (drives WP7 persistence).
  useEffect(() => {
    onProgress?.(reading)
  }, [reading, onProgress])

  // Report each reached ending at most once per session. A set of completed ending
  // ids (not a single last-seen ref) makes this idempotent across three hazards: the
  // <StrictMode> double-invoke of this effect, RESTART re-entering the same ending,
  // and reaching an ending again after visiting a different one first. A single-slot
  // ref would miss that last case and re-fire onComplete for an earlier ending.
  const completedEndingsRef = useRef<Set<string>>(new Set())
  useEffect(() => {
    if (!snapshot.matches('ended')) {
      return
    }
    const endingId = currentEndingId(story, reading)
    // #CRITICAL: timing/data-integrity: StrictMode double-invokes this effect, and
    // RESTART can re-reach an ending (the same one, or one visited earlier); each
    // distinct ending must post at most once.
    // #VERIFY: gate on a set of completed ending ids so only a not-yet-seen ending
    // fires onComplete (aligned with the server's per-ending completion dedup key).
    if (endingId === null || completedEndingsRef.current.has(endingId)) {
      return
    }
    completedEndingsRef.current.add(endingId)
    onComplete?.(endingId)
  }, [snapshot, story, reading, onComplete])

  // choose() throws on a structurally invalid transition (dangling choice
  // target, corrupted cached state); that is deliberate engine behavior
  // shared with the Python conformance corpus, not something to silently
  // swallow inside the engine itself. The machine's applyChoice action
  // catches it (machine.ts) and surfaces it as context.error instead: XState
  // catches an assign() throw internally and permanently stops the actor,
  // so catching it here, after send() returns, would be too late.
  const choose = (choiceId: string): void => {
    // Read-aloud must never talk over the next passage; a choice tap is
    // navigation within the same mounted Reader (no unmount), so this is not
    // covered by the hook's unmount cleanup.
    readAloud.stop()
    recordInteraction()
    send({ type: 'CHOOSE', choiceId })
  }

  // Tapping the read-aloud toggle: start speaking the current passage (then
  // its visible choices), or stop if already speaking. Never auto-plays; the
  // only way speech starts is this explicit tap.
  const handleToggleSpeak = (): void => {
    if (readAloud.speaking) {
      readAloud.stop()
    } else {
      // The third argument is the TTS egress guard's generic fallback: a
      // non-local voice speaks the generic text, never the child's name.
      readAloud.speak(
        bodyText,
        choices.map((choice) => choice.label),
        genericBodyText
      )
    }
  }

  // Whenever the node changes, in either direction (a choice forward or Go
  // back), bring the passage into view from its top and move focus to it so a
  // screen reader announces the passage from its start. Keyed on the last-seen
  // node (not a first-run flag) so the initial mount never steals focus, and
  // the StrictMode double-invoke of this effect stays a no-op (the ref already
  // matches on the second run).
  const passageRef = useRef<HTMLDivElement>(null)
  const lastNodeRef = useRef(reading.current_node)
  useEffect(() => {
    if (lastNodeRef.current === reading.current_node) {
      return
    }
    lastNodeRef.current = reading.current_node
    // #EDGE: browser-compat: jsdom implements neither matchMedia nor a real
    // scrollTo; optional-call both (same guard as scrollIntoView elsewhere)
    // and treat a missing matchMedia as "no reduced-motion preference".
    // The guardian-set per-profile reduce_motion flag rides in as
    // data-reduce-motion on the kid shell (see band-tokens.css), so honor it
    // alongside the OS preference for this one JS-driven animation too.
    const reduceMotion =
      (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false) ||
      Boolean(passageRef.current?.closest('[data-reduce-motion="true"]'))
    window.scrollTo?.({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' })
    passageRef.current?.focus?.({ preventScroll: true })
  }, [reading.current_node])

  // An always-visible exit: a child can leave a story at any point, not only
  // from the ending screen. It reads as "Leave" rather than a bare arrow so the
  // action is unmistakable to a young reader. When the owner passes onLeave it
  // takes over the tap (ReaderPage uses it to settle an in-flight progress save
  // before unmounting; see "surfaces a lost save..." in ReaderLeave.test.tsx);
  // otherwise Leave navigates to the profile's library directly.
  const leaveButton = (
    <button
      type="button"
      className="reader-leave"
      onClick={() => {
        // Read-aloud must never keep talking after the child has left.
        readAloud.stop()
        const leave = onLeave ?? (() => void navigate(`/library/${profileId}`))
        leave()
      }}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M15 5 L8 12 L15 19"
        />
      </svg>
      Leave
    </button>
  )

  // Kids mis-tap constantly; Go back undoes just the last choice (page bands)
  // or the last STOP (ADR-026 decision 3, flowed bands) by replaying the
  // recorded path through the deterministic engine (machine BACK event),
  // instead of forcing a full restart. Hidden entirely (not disabled) when
  // there is nothing to undo: at the start node, and for states the engine
  // cannot faithfully replay (continuation reads).
  // #ASSUME: timing dependencies: at a flowed band, by the time this renders
  // the live `reading` already sits at the current stop's TERMINAL node
  // (useFlowedStop's silent advance -- see that module's doc), matching what
  // `backOneStop`/`canGoBackOneStop` (player/stops.ts) assume their input
  // state represents. `goBackSteps` back() calls through the existing BACK
  // event therefore reproduces `backOneStop`'s own "call back() once per node
  // in the stop" algorithm exactly, without needing a "jump to this state"
  // machine event this integration must not add (see useFlowedStop.ts).
  // #VERIFY: Reader.test.tsx "go back at a flowed band rewinds the whole
  // stop, landing on the previous stop's terminal choice, not mid-flow".
  //
  // #CRITICAL: data-integrity: this availability check and the machine's BACK
  // guard (machine.ts: `canGoBack(context.story, context.reading,
  // context.seed)`) MUST be computed from the same seed. `back()` replays the
  // recorded path from the read's own start and accepts only an exact
  // var_state match, so a seed-blind availability check disagrees with the
  // seed-aware guard on every seeded read: the button renders and the BACK
  // event is silently swallowed (a dead control on the kid surface), or the
  // inverse hides a button that would have worked. Passing `seed` on BOTH
  // branches is what keeps the two in lock-step; a future branch added here
  // must pass it too.
  // #VERIFY: Reader.test.tsx "the Go back button and the BACK event agree on a
  // seeded read" pins the non-flowed branch (no `ageBand`, so `flowedStop` is
  // null there); "the flowed branch's Go back button and the BACK event agree
  // on a seeded read" pins the flowed branch above by rendering a Reader that
  // is both flowed AND seeded. stops.test.ts "rewinds a stop on a seeded read
  // only when the seed is forwarded" only proves stops.ts forwards the
  // parameter it is given; it cannot observe whether this call site passes
  // one at all, so it does not pin the flowed branch by itself.
  const canUndo = useMemo(
    () =>
      flowedStop ? canGoBackOneStop(story, flowedStop, seed) : canGoBack(story, reading, seed),
    [story, reading, flowedStop, seed]
  )
  const goBackSteps = flowedStop ? flowedStop.nodeIds.length : 1
  // Labelled "Go back a page" (not bare "Go back"): on the ending screen it
  // sits beside "Back to my books", and two unqualified "back"s left a young
  // reader guessing which one stays in the story. Kept as-is at flowed bands
  // too (not "Go back a stop"): from a child's seat it is still "undo my
  // last tap", the same action it has always been.
  const goBackButton = canUndo ? (
    <Button
      variant="ghost"
      data-testid="go-back"
      onClick={() => {
        // Going back changes the current node without unmounting the Reader,
        // so read-aloud must be stopped explicitly here.
        readAloud.stop()
        recordInteraction()
        for (let i = 0; i < goBackSteps; i += 1) {
          send({ type: 'BACK' })
        }
      }}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M15 5 L8 12 L15 19"
        />
      </svg>
      Go back a page
    </Button>
  ) : null

  // W1.2/AL-029: `position.complete` is the one moment the chrome shows a
  // real percent -- the story is genuinely, truly done. Otherwise it is the
  // plain "Page N" position label (readerProgress.ts), never a percent: the
  // graph has no honest "how much is left on the path this child took"
  // figure to fill a bar toward (see that module's doc for why).
  const ended = snapshot.matches('ended')
  // The read-aloud toggle only makes sense while there is a real passage to
  // read (the normal reading and ending screens); the stuck-page error
  // screen below shares `chrome` but never gets the toggle, so a child is
  // never invited to hear a page that failed to render. `readAloud.available`
  // already folds in both the profile's tts_enabled flag and browser
  // support, so omitting the prop when it's false keeps ReaderChrome from
  // rendering a dead button.
  const chrome = (
    <ReaderChrome
      position={
        ended
          ? { label: 'You finished this story!', complete: true }
          : { label: readerPositionLabel(story, reading, ageBand) }
      }
      characterName={characterName}
      back={leaveButton}
      fontControl={<TextSizeControl fontScale={fontScale} />}
      readAloud={
        !choiceError && readAloud.available
          ? { speaking: readAloud.speaking, onToggle: handleToggleSpeak }
          : undefined
      }
      flag={
        submitFlag ? (
          <FlagButton
            profileId={profileId}
            storybookId={story.id}
            version={story.version}
            getNodeId={() => reading.current_node}
            submitFlag={submitFlag}
          />
        ) : undefined
      }
    />
  )

  // The chosen text size is applied as a CSS custom property on each reader
  // shell so PassageText prose scales in every phase (reading, ending, error).
  const shellStyle = { '--reader-font-scale': String(fontScale.scale) } as CSSProperties

  if (choiceError) {
    return (
      <div className="reader-shell" style={shellStyle} ref={shellRef}>
        {chrome}
        <section className="reader-error" role="alert">
          <Mascot size={96} className="reader-error__mascot" />
          <h2 className="reader-error__title">Hmm, that page got stuck.</h2>
          <p className="reader-error__body">Let&apos;s start this story over so it works right.</p>
          <div className="reader-error__actions">
            <Button
              variant="primary"
              size="lg"
              onClick={() => {
                readAloud.stop()
                send({ type: 'RESTART' })
              }}
            >
              Start over
            </Button>
            <BackToLibrary profileId={profileId} />
          </div>
        </section>
      </div>
    )
  }

  if (ended) {
    const ending = node?.ending
    const meta = seriesMeta(story)
    const showContinue =
      fetchSeriesNext !== undefined &&
      meta !== null &&
      !meta.isFinal &&
      SATISFYING_ENDING_KINDS.has(ending?.kind ?? '')
    // Positive and neutral endings get the animated star burst (pure CSS,
    // stilled under prefers-reduced-motion); a sad or cliffhanger ending
    // (negative valence) keeps the same warm static stars without the pop so
    // the screen stays kind rather than gleeful. An ending without valence
    // data celebrates: finishing a story is a win by default.
    const celebrate = ending?.valence !== 'negative'
    return (
      <div className="reader-shell" style={shellStyle} ref={shellRef}>
        {chrome}
        <section data-testid="ending-screen" className="reader-ending">
          <div
            data-testid="ending-celebration"
            className={
              celebrate
                ? 'reader-ending__stars reader-ending__stars--celebrate'
                : 'reader-ending__stars'
            }
            aria-hidden="true"
          >
            <span>★</span>
            <span>★</span>
            <span>★</span>
          </div>
          <Mascot
            size={112}
            className={
              celebrate
                ? 'reader-ending__mascot reader-ending__mascot--celebrate'
                : 'reader-ending__mascot'
            }
          />
          <h2 className="reader-ending__title">{endingTitle === '' ? 'The End' : endingTitle}</h2>
          <div
            ref={passageRef}
            tabIndex={-1}
            data-testid="passage-body"
            className="reader-ending__body"
            aria-live="polite"
          >
            <PassageText text={bodyText} highlightRange={readAloud.spokenWordRange} />
          </div>
          <p data-testid="ending-id" hidden>
            {currentEndingId(story, reading) ?? ''}
          </p>
          {fetchReadingHistory ? (
            <EndingsProgress
              profileId={profileId}
              storybookId={story.id}
              fetchReadingHistory={fetchReadingHistory}
              completionOutcome={completionOutcome}
            />
          ) : null}
          {/* W3.2: the Endings Gallery's ending-screen entry point. Omitted
              entirely (no button) when the caller has no progress port
              wired, mirroring fetchReadingHistory's own optional pattern. */}
          {progressApi ? (
            <EndingsGalleryButton
              profileId={profileId}
              storybookId={story.id}
              bookTitle={story.title}
              api={progressApi}
            />
          ) : null}
          {/* W3.2: badge-unlock toast. The caller (ReaderPage) decides WHICH
              badge (pre/post progress comparison + IndexedDB seen-state);
              this only renders whatever it is handed and clears it on
              dismiss (tap or auto-dismiss). */}
          {newlyEarnedBadge ? (
            <BadgeUnlockToast badge={newlyEarnedBadge} onDismiss={() => onDismissBadgeToast?.()} />
          ) : null}
          <div className="reader-ending__actions">
            <Button
              variant="primary"
              size="lg"
              data-testid="restart"
              onClick={() => {
                readAloud.stop()
                recordInteraction()
                send({ type: 'RESTART' })
              }}
            >
              Read again
            </Button>
            {/* "Go back a page" is where try-the-other-path value peaks: it
                returns into the story one step before this ending. */}
            {goBackButton}
            <BackToLibrary profileId={profileId} />
            {showContinue && meta && fetchSeriesNext ? (
              <ContinueSeries
                profileId={profileId}
                storybookId={story.id}
                fetchSeriesNext={fetchSeriesNext}
                finalVarState={reading.var_state}
                carriesState={meta.carriesState}
              />
            ) : null}
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="reader-shell" style={shellStyle} ref={shellRef}>
      {chrome}
      <section data-testid="reader" className="reader">
        {atOpening ? <DedicationOverlay personalization={personalization} /> : null}
        <div
          ref={passageRef}
          tabIndex={-1}
          data-testid="passage-body"
          className="reader-passage"
          aria-live="polite"
        >
          <PassageText text={bodyText} highlightRange={readAloud.spokenWordRange} />
        </div>
        <ul className="reader-choices">
          {choices.map((choice) => (
            <li key={choice.id}>
              <ChoiceButton
                label={choice.label}
                data-testid={`choice-${choice.id}`}
                onClick={() => choose(choice.id)}
              />
            </li>
          ))}
        </ul>
        {/* Below the choices, not among them, so undoing a mis-tap never
            competes with the story's own options. */}
        {goBackButton ? <div className="reader-back-row">{goBackButton}</div> : null}
      </section>
    </div>
  )
}
