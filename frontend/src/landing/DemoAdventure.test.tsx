import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { DemoAdventure } from './DemoAdventure'
import { DEMO_STORY } from './demoStory'

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
    expect(screen.getByRole('link', { name: /make their next story/i })).toHaveAttribute(
      'href',
      '/guardian/login'
    )
  })

  it('restarts from the beginning via "Read it again"', () => {
    renderDemo()
    fireEvent.click(screen.getByRole('button', { name: /climb the mossy stairs/i }))
    fireEvent.click(screen.getByRole('button', { name: /race the boat along the bank/i }))
    expect(screen.getByText('Won by a Whisker')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /read it again/i }))
    expect(screen.getByText(/brass lantern swings/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /slip into the glittering cave/i })).toBeVisible()
  })

  it('has choices for every non-ending node and an ending title for every ending', () => {
    // Guards the demo content's shape: a node with neither choices nor an
    // ending title would render a dead end with no way forward and no outro.
    for (const node of Object.values(DEMO_STORY)) {
      if (node.choices) {
        expect(node.choices.length).toBeGreaterThan(0)
        for (const choice of node.choices) {
          expect(DEMO_STORY[choice.to]).toBeDefined()
        }
      } else {
        expect(node.endingTitle).toBeTruthy()
      }
    }
  })
})
