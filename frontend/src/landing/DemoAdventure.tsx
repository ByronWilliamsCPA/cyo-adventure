import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@ds/components/Button'
import { ChoiceButton } from '@ds/components/ChoiceButton'
import { GUARDIAN_LOGIN_PATH } from '../routes'

import { DEMO_ENDING_COUNT, DEMO_START, DEMO_STORY } from './demoStory'
import type { DemoNodeId } from './demoStory'

/**
 * Interactive sample adventure for the landing page's funnel: a real, working
 * two-hop choose-your-own story rendered with the SAME ChoiceButton primitive
 * the reader uses, so "what the product feels like" is demonstrated rather
 * than described. Pure client state over the static demoStory.ts content;
 * no fetching, no player engine, nothing kid-account-related, keeping the
 * landing chunk's no-data-no-auth contract intact.
 *
 * Focus management: choosing replaces the passage (and its buttons), which
 * would otherwise drop keyboard focus to <body> and strand a screen-reader
 * user mid-story. Each transition moves focus to the new passage instead
 * (tabIndex={-1} container), which also announces the fresh text. The
 * initial mount deliberately does NOT steal focus; only user-driven
 * transitions do.
 */
export function DemoAdventure() {
  const [nodeId, setNodeId] = useState<DemoNodeId>(DEMO_START)
  const passageRef = useRef<HTMLDivElement | null>(null)
  const interactedRef = useRef(false)

  const node = DEMO_STORY[nodeId]
  const isEnding = !node.choices

  useEffect(() => {
    if (!interactedRef.current) return
    passageRef.current?.focus()
  }, [nodeId])

  function goTo(next: DemoNodeId) {
    interactedRef.current = true
    setNodeId(next)
  }

  return (
    <div className="demo-adventure">
      <div
        className="demo-adventure__passage"
        ref={passageRef}
        tabIndex={-1}
        data-testid="demo-passage"
      >
        {isEnding ? (
          <p className="demo-adventure__ending-kicker">
            The End: <strong>{node.endingTitle}</strong>
          </p>
        ) : null}
        <p className="demo-adventure__text">{node.text}</p>
      </div>

      {node.choices ? (
        <div className="demo-adventure__choices">
          {node.choices.map((choice) => (
            <ChoiceButton key={choice.to} label={choice.label} onClick={() => goTo(choice.to)} />
          ))}
        </div>
      ) : (
        <div className="demo-adventure__outro">
          <p className="demo-adventure__found">
            You found 1 of {DEMO_ENDING_COUNT} endings. Real books hide even more, and every path is
            written for your reader and approved by you.
          </p>
          <div className="demo-adventure__outro-actions">
            <Button variant="ghost" onClick={() => goTo(DEMO_START)}>
              Read it again
            </Button>
            <Link className="landing-cta landing-cta--primary" to={GUARDIAN_LOGIN_PATH}>
              Make their next story
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
