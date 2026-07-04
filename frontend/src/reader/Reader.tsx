/**
 * The story reader UI.
 *
 * Drives the XState reader machine and renders the current passage with only the
 * visible choices (a false-condition choice is hidden, not disabled, per the
 * runtime semantics). On an ending node it shows the ending screen. Composes the
 * design-system components (PassageText, ChoiceButton) and a persistent top bar.
 */

import { useEffect, useRef } from 'react'

import { Button } from '@ds/components/Button'
import { ChoiceButton } from '@ds/components/ChoiceButton'
import { PassageText } from '@ds/components/PassageText'
import { useMachine } from '@xstate/react'

import { currentEndingId, visibleChoices } from '../player/engine'
import { readerMachine } from '../player/machine'
import type { ReadingState, Storybook } from '../player/types'
import { BackToLibrary } from './BackToLibrary'
import { ReaderChrome } from './ReaderChrome'
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
}

export function Reader({ story, initialReading, onProgress, onComplete, profileId }: ReaderProps) {
  const [snapshot, send] = useMachine(readerMachine, {
    input: { story, reading: initialReading },
  })
  const { reading } = snapshot.context
  const node = story.nodes.find((n) => n.id === reading.current_node)

  // Report progress whenever the reading state changes (drives WP7 persistence).
  useEffect(() => {
    onProgress?.(reading)
  }, [reading, onProgress])

  // Report the reached ending exactly once. A per-ending ref makes this idempotent
  // across two hazards: the <StrictMode> double-invoke of this effect, and RESTART
  // re-entering the same ending later in the session.
  const completedEndingRef = useRef<string | null>(null)
  useEffect(() => {
    if (!snapshot.matches('ended')) {
      return
    }
    const endingId = currentEndingId(story, reading)
    // #CRITICAL: timing/data-integrity: StrictMode double-invokes this effect, and
    // RESTART can re-reach the same ending; both must post at most once.
    // #VERIFY: gate on a per-ending ref so only a NEW ending id fires onComplete.
    if (endingId === null || completedEndingRef.current === endingId) {
      return
    }
    completedEndingRef.current = endingId
    onComplete?.(endingId)
  }, [snapshot, story, reading, onComplete])

  const choose = (choiceId: string): void => {
    send({ type: 'CHOOSE', choiceId })
  }

  // showLabel is left at its default (hidden): the percent's denominator is all
  // of the story's nodes, not the reachable subset for this branch, so it can
  // never hit 100% on a real playthrough. The bar's fill and aria-label still
  // convey progress; only the misleading numeric text is withheld.
  const chrome = (
    <ReaderChrome
      percent={readerProgressPercent(story, reading)}
      label={readerProgressLabel(story, reading)}
    />
  )

  if (snapshot.matches('ended')) {
    const ending = node?.ending
    return (
      <div className="reader-shell">
        {chrome}
        <section data-testid="ending-screen" className="reader-ending">
          <h2 className="reader-ending__title">{ending?.title ?? 'The End'}</h2>
          <div data-testid="passage-body">
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
            <BackToLibrary profileId={profileId} />
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="reader-shell">
      {chrome}
      <section data-testid="reader" className="reader">
        <div data-testid="passage-body">
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
      </section>
    </div>
  )
}
