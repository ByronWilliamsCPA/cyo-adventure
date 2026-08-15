import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { DemoAdventure } from './DemoAdventure'
import { DEMO_ENDING_COUNT, DEMO_START, DEMO_STORY } from './demoStory'
import type { DemoNodeId } from './demoStory'

function renderDemo() {
  return render(
    <MemoryRouter>
      <DemoAdventure />
    </MemoryRouter>
  )
}

describe('DemoAdventure', () => {
  it('starts at the opening passage with its two choices', () => {
    renderDemo()
    expect(screen.getByText(/brass lantern swings/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /slip into the glittering cave/i })).toBeVisible()
    expect(screen.getByRole('button', { name: /climb the mossy stairs/i })).toBeVisible()
  })

  it('advances to the chosen branch and moves focus to the fresh passage', () => {
    renderDemo()
    fireEvent.click(screen.getByRole('button', { name: /slip into the glittering cave/i }))
    expect(screen.getByText(/walls sparkle like a sky full of green stars/i)).toBeInTheDocument()
    // The choice buttons the user was focused on are gone; focus lands on the
    // new passage so keyboard and screen-reader users are not stranded.
    expect(screen.getByTestId('demo-passage')).toHaveFocus()
  })

  it('reaches an ending, pitches the product, and links the CTA to guardian login', () => {
    renderDemo()
    fireEvent.click(screen.getByRole('button', { name: /slip into the glittering cave/i }))
    fireEvent.click(screen.getByRole('button', { name: /peek behind the stone/i }))

    expect(screen.getByText('A New Friend')).toBeInTheDocument()
    expect(screen.getByText(DEMO_STORY.end_glowbug.text)).toBeInTheDocument()
    expect(screen.getByText(/you found 1 of 4 endings/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Get started free' })).toHaveAttribute(
      'href',
      '/guardian/login'
    )
  })

  // The outro invites a replay, so the counter must survive it: a "1 of 4"
  // that never moved after a second ending made the demo look broken at the
  // exact moment it asked for engagement. "Back one choice" (the demo's
  // miniature of the reader's real go-back feature) is the cheap route to a
  // sibling ending and must land on the ending's actual parent scene.
  it('counts endings across replays, including via Back one choice', () => {
    renderDemo()
    fireEvent.click(screen.getByRole('button', { name: /slip into the glittering cave/i }))
    fireEvent.click(screen.getByRole('button', { name: /peek behind the stone/i }))
    expect(screen.getByText(/you found 1 of 4 endings/i)).toBeInTheDocument()

    // Back one choice returns to the cave scene, not the start.
    fireEvent.click(screen.getByRole('button', { name: /back one choice/i }))
    expect(screen.getByText(/walls sparkle like a sky full of green stars/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /giggle back, twice/i }))
    expect(screen.getByText(/you found 2 of 4 endings/i)).toBeInTheDocument()

    // Revisiting an already-found ending does not double-count.
    fireEvent.click(screen.getByRole('button', { name: /back one choice/i }))
    fireEvent.click(screen.getByRole('button', { name: /peek behind the stone/i }))
    expect(screen.getByText(/you found 2 of 4 endings/i)).toBeInTheDocument()
  })

  it('celebrates completion (with the badges pitch) once every ending is found', () => {
    renderDemo()
    const paths: [RegExp, RegExp][] = [
      [/slip into the glittering cave/i, /peek behind the stone/i],
      [/slip into the glittering cave/i, /giggle back, twice/i],
      [/climb the mossy stairs/i, /splash in and rescue the letter/i],
      [/climb the mossy stairs/i, /race the boat along the bank/i],
    ]
    paths.forEach(([first, second], index) => {
      fireEvent.click(screen.getByRole('button', { name: first }))
      fireEvent.click(screen.getByRole('button', { name: second }))
      // Restart between paths; after the last ending, stay on the outro so
      // the completion state below is what renders.
      if (index < paths.length - 1) {
        fireEvent.click(screen.getByRole('button', { name: /start over/i }))
      }
    })
    expect(screen.getByText(/you found all 4 endings!/i)).toBeInTheDocument()
    expect(screen.getByText(/earns badges/i)).toBeInTheDocument()
  })

  it('restarts from the beginning via "Start over"', () => {
    renderDemo()
    fireEvent.click(screen.getByRole('button', { name: /climb the mossy stairs/i }))
    fireEvent.click(screen.getByRole('button', { name: /race the boat along the bank/i }))
    expect(screen.getByText('Won by a Whisker')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /start over/i }))
    expect(screen.getByText(/brass lantern swings/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /slip into the glittering cave/i })).toBeVisible()
  })

  // Structural guards on the story data itself. The DemoNode union already
  // makes a dead end (no choices, no ending) a type error; these pin the
  // graph properties the type cannot express.
  it('keeps every node reachable and every ending exactly two choices from the start', () => {
    const reachable = new Set<DemoNodeId>([DEMO_START])
    let frontier: DemoNodeId[] = [DEMO_START]
    let depth = 0
    const endingDepths: number[] = []
    while (frontier.length > 0) {
      const next: DemoNodeId[] = []
      for (const id of frontier) {
        const node = DEMO_STORY[id]
        if (node.endingTitle !== undefined) {
          endingDepths.push(depth)
          continue
        }
        for (const choice of node.choices) {
          expect(DEMO_STORY[choice.to]).toBeDefined()
          if (!reachable.has(choice.to)) {
            reachable.add(choice.to)
            next.push(choice.to)
          }
        }
      }
      frontier = next
      depth += 1
    }
    // Every authored node is reachable (no orphans)...
    expect(reachable.size).toBe(Object.keys(DEMO_STORY).length)
    // ...every ending sits exactly two hops in (the docstring's promise)...
    expect(endingDepths).toHaveLength(DEMO_ENDING_COUNT)
    for (const endingDepth of endingDepths) {
      expect(endingDepth).toBe(2)
    }
    // ...and the derived ending count matches the graph.
    const endings = Object.values(DEMO_STORY).filter((n) => n.endingTitle !== undefined)
    expect(DEMO_ENDING_COUNT).toBe(endings.length)
  })
})
