/**
 * The story reader UI.
 *
 * Drives the XState reader machine and renders the current passage with only the
 * visible choices (a false-condition choice is hidden, not disabled, per the
 * runtime semantics). On an ending node it shows the ending screen.
 */

import { useEffect } from 'react'

import { useMachine } from '@xstate/react'

import { currentEndingId, visibleChoices } from '../player/engine'
import { readerMachine } from '../player/machine'
import type { ReadingState, Storybook } from '../player/types'

export interface ReaderProps {
  story: Storybook
  initialReading?: ReadingState
  onProgress?: (reading: ReadingState) => void
}

export function Reader({ story, initialReading, onProgress }: ReaderProps) {
  const [snapshot, send] = useMachine(readerMachine, {
    input: { story, reading: initialReading },
  })
  const { reading } = snapshot.context
  const node = story.nodes.find((n) => n.id === reading.current_node)

  // Report progress whenever the reading state changes (drives WP7 persistence).
  useEffect(() => {
    onProgress?.(reading)
  }, [reading, onProgress])

  const choose = (choiceId: string): void => {
    send({ type: 'CHOOSE', choiceId })
  }

  if (snapshot.matches('ended')) {
    const ending = node?.ending
    return (
      <section data-testid="ending-screen" className="reader-ending">
        <h2>{ending?.title ?? 'The End'}</h2>
        <p data-testid="passage-body">{node?.body}</p>
        <p data-testid="ending-id" hidden>
          {currentEndingId(story, reading) ?? ''}
        </p>
        <button type="button" data-testid="restart" onClick={() => send({ type: 'RESTART' })}>
          Read again
        </button>
      </section>
    )
  }

  return (
    <section data-testid="reader" className="reader">
      <p data-testid="passage-body">{node?.body}</p>
      <ul className="reader-choices">
        {visibleChoices(story, reading).map((choice) => (
          <li key={choice.id}>
            <button
              type="button"
              data-testid={`choice-${choice.id}`}
              onClick={() => choose(choice.id)}
            >
              {choice.label}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
