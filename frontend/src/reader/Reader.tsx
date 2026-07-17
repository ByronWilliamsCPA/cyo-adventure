/**
 * The story reader UI.
 *
 * Drives the XState reader machine and renders the current passage with only the
 * visible choices (a false-condition choice is hidden, not disabled, per the
 * runtime semantics). On an ending node it shows the ending screen. Composes the
 * design-system components (PassageText, ChoiceButton) and a persistent top bar.
 */

import { useEffect, useMemo, useRef, type CSSProperties } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@ds/components/Button'
import { ChoiceButton } from '@ds/components/ChoiceButton'
import { PassageText } from '@ds/components/PassageText'
import { useMachine } from '@xstate/react'

import type { SeriesNextBookInfo } from '../api/readerApi'
import { canGoBack, currentEndingId, visibleChoices } from '../player/engine'
import { Mascot } from '../kid/Mascot'
import { readerMachine } from '../player/machine'
import { SATISFYING_ENDING_KINDS, seriesMeta } from '../player/series'
import type { ReadingState, Storybook } from '../player/types'
import { BackToLibrary } from './BackToLibrary'
import { ContinueSeries } from './ContinueSeries'
import { ReaderChrome } from './ReaderChrome'
import { TextSizeControl } from './TextSizeControl'
import { useReaderFontScale } from './useReaderFontScale'
import { readerProgressLabel, readerProgressPercent } from './readerProgress'
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
  fetchSeriesNext?: (
    profileId: string,
    storybookId: string
  ) => Promise<SeriesNextBookInfo | null>
}

export function Reader({
  story,
  initialReading,
  onProgress,
  onComplete,
  profileId,
  onLeave,
  fetchSeriesNext,
}: ReaderProps) {
  const navigate = useNavigate()
  const fontScale = useReaderFontScale(profileId)
  const [snapshot, send] = useMachine(readerMachine, {
    input: { story, reading: initialReading },
  })
  const { reading, error: choiceError } = snapshot.context
  const node = story.nodes.find((n) => n.id === reading.current_node)

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
    send({ type: 'CHOOSE', choiceId })
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
    const reduceMotion =
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
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
      onClick={onLeave ?? (() => void navigate(`/library/${profileId}`))}
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

  // Kids mis-tap constantly; Go back undoes just the last choice by replaying
  // the recorded path through the deterministic engine (machine BACK event),
  // instead of forcing a full restart. Hidden entirely (not disabled) when
  // there is nothing to undo: at the start node, and for states the engine
  // cannot faithfully replay (continuation reads). canGoBack replays the path
  // to answer, so memoize it per reading state rather than per render.
  const canUndo = useMemo(() => canGoBack(story, reading), [story, reading])
  const goBackButton = canUndo ? (
    <Button variant="ghost" data-testid="go-back" onClick={() => send({ type: 'BACK' })}>
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
      Go back
    </Button>
  ) : null

  // showLabel is left at its default (hidden): the percent's denominator is all
  // of the story's nodes, not the reachable subset for this branch, so it can
  // never hit 100% on a real playthrough. The bar's fill and aria-label still
  // convey progress; only the misleading numeric text is withheld. On an
  // ending the bar is forced full: the story is done, and a finished story
  // must never look unfinished to the child who just finished it.
  const ended = snapshot.matches('ended')
  const chrome = (
    <ReaderChrome
      percent={ended ? 100 : readerProgressPercent(story, reading)}
      label={ended ? 'You finished this story!' : readerProgressLabel(story, reading)}
      back={leaveButton}
      fontControl={<TextSizeControl fontScale={fontScale} />}
    />
  )

  // The chosen text size is applied as a CSS custom property on each reader
  // shell so PassageText prose scales in every phase (reading, ending, error).
  const shellStyle = { '--reader-font-scale': String(fontScale.scale) } as CSSProperties

  if (choiceError) {
    return (
      <div className="reader-shell" style={shellStyle}>
        {chrome}
        <section className="reader-error" role="alert">
          <Mascot size={96} className="reader-error__mascot" />
          <h2 className="reader-error__title">Hmm, that page got stuck.</h2>
          <p className="reader-error__body">
            Let&apos;s start this story over so it works right.
          </p>
          <div className="reader-error__actions">
            <Button
              variant="primary"
              size="lg"
              onClick={() => send({ type: 'RESTART' })}
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
      <div className="reader-shell" style={shellStyle}>
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
          <h2 className="reader-ending__title">{ending?.title ?? 'The End'}</h2>
          <div
            ref={passageRef}
            tabIndex={-1}
            data-testid="passage-body"
            className="reader-ending__body"
            aria-live="polite"
          >
            <PassageText text={node?.body ?? ''} />
          </div>
          <p data-testid="ending-id" hidden>
            {currentEndingId(story, reading) ?? ''}
          </p>
          <div className="reader-ending__actions">
            <Button
              variant="primary"
              size="lg"
              data-testid="restart"
              onClick={() => send({ type: 'RESTART' })}
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
    <div className="reader-shell" style={shellStyle}>
      {chrome}
      <section data-testid="reader" className="reader">
        <div
          ref={passageRef}
          tabIndex={-1}
          data-testid="passage-body"
          className="reader-passage"
          aria-live="polite"
        >
          <PassageText text={node?.body ?? ''} />
        </div>
        <ul className="reader-choices">
          {visibleChoices(story, reading).map((choice) => (
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
