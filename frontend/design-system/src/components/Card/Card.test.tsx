import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Card } from './Card'

describe('Card', () => {
  it('renders children inside the card surface', () => {
    render(<Card>Chapter 1: The Beginning</Card>)
    expect(screen.getByText('Chapter 1: The Beginning')).toBeInTheDocument()
  })

  it('defaults to non-interactive: no hover-lift modifier class', () => {
    render(<Card>Row content</Card>)
    expect(screen.getByText('Row content').className).not.toContain('cyo-card--interactive')
  })

  it('adds the interactive modifier class when interactive is set', () => {
    render(<Card interactive>Row content</Card>)
    expect(screen.getByText('Row content').className).toContain('cyo-card--interactive')
  })

  it('forwards className and other div props', () => {
    render(
      <Card className="console-row" data-testid="my-card">
        Row content
      </Card>,
    )
    const card = screen.getByTestId('my-card')
    expect(card.className).toContain('cyo-card')
    expect(card.className).toContain('console-row')
  })
})
