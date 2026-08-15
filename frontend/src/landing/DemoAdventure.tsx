import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@ds/components/Button'
import { ChoiceButton } from '@ds/components/ChoiceButton'
import { GUARDIAN_LOGIN_PATH } from '../routes'

import { DEMO_ENDING_COUNT, DEMO_PARENTS, DEMO_START, DEMO_STORY } from './demoStory'
import type { DemoNodeId } from './demoStory'

/**
 * Interactive sample adventure for the landing page's funnel: a real, working
 * two-hop choose-your-own story rendered with the SAME ChoiceButton primitive
 * the reader uses, so "what the product feels like" is demonstrated rather
 * than described. Pure client state over the static demoStory.ts content;
 * no fetching, no player engine, nothing kid-account-related, keeping the
 * landing chunk's no-data-no-auth contract intact.
 *
 * Endings found are tracked across replays ("You found 2 of 4"), because the
 * outro explicitly invites a replay: a counter that stayed at 1 after the
 * second ending would make the demo look broken at the exact moment it asked
 * for engagement. The outro offers both "Back one choice" (the demo's
 * miniature of the reader's real go-back feature, and the cheap route to a
 * sibling ending) and a full restart. Finding all of them swaps in a
 * completion line that carries the badges pitch, the one place that idea
 * lands better than a feature card.
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
  const [foundEndings, setFoundEndings] = useState<ReadonlySet<DemoNodeId>>(new Set())
  const passageRef = useRef<HTMLDivElement | null>(null)
  const interactedRef = useRef(false)

  const node = DEMO_STORY[nodeId]
  const isEnding = node.endingTitle !== undefined
  const parentId = DEMO_PARENTS[nodeId]
  const foundAll = foundEndings.size === DEMO_ENDING_COUNT

  useEffect(() => {
    if (!interactedRef.current) return
    passageRef.current?.focus()
  }, [nodeId])

  function goTo(next: DemoNodeId) {
    interactedRef.current = true
    if (DEMO_STORY[next].endingTitle !== undefined) {
      setFoundEndings((prev) => (prev.has(next) ? prev : new Set(prev).add(next)))
    }
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
            {foundAll
              ? `You found all ${DEMO_ENDING_COUNT} endings! In real books, finding every ` +
                'ending earns badges worth bragging about at dinner.'
              : `You found ${foundEndings.size} of ${DEMO_ENDING_COUNT} endings. Real books run ` +
                'much bigger, from a couple dozen passages for the youngest readers to a few ' +
                'hundred for a ten-year-old, every path approved by you.'}
          </p>
          <div className="demo-adventure__outro-actions">
            {parentId ? (
              <Button variant="ghost" onClick={() => goTo(parentId)}>
                Back one choice
              </Button>
            ) : null}
            <Button variant="ghost" onClick={() => goTo(DEMO_START)}>
              Start over
            </Button>
            <Link className="landing-cta landing-cta--primary" to={GUARDIAN_LOGIN_PATH}>
              Get started free
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
