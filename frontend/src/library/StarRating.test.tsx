import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { StarRating } from './StarRating'

describe('StarRating', () => {
  it('renders five stars with the current value filled', () => {
    render(<StarRating value={3} onRate={() => {}} bookTitle="The Lantern" />)
    const group = screen.getByRole('group', { name: /rate the lantern/i })
    const buttons = screen.getAllByRole('button')
    expect(group).toBeInTheDocument()
    expect(buttons).toHaveLength(5)
    expect(buttons[2]).toHaveAttribute('aria-pressed', 'true')
    expect(buttons[3]).toHaveAttribute('aria-pressed', 'false')
  })

  it('reports the tapped star value', () => {
    const onRate = vi.fn()
    render(<StarRating value={null} onRate={onRate} bookTitle="T" />)
    fireEvent.click(screen.getByRole('button', { name: /4 stars/i }))
    expect(onRate).toHaveBeenCalledWith(4)
  })

  it('stops card-level navigation when a star is tapped', () => {
    const onRate = vi.fn()
    const outer = vi.fn()
    render(
      <a href="/somewhere" onClick={(e) => { e.preventDefault(); outer() }}>
        <StarRating value={2} onRate={onRate} bookTitle="T" />
      </a>
    )
    fireEvent.click(screen.getByRole('button', { name: /5 stars/i }))
    expect(onRate).toHaveBeenCalledWith(5)
    expect(outer).not.toHaveBeenCalled()
  })
})
