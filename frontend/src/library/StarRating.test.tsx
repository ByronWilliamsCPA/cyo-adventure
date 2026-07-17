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

  it('labels every star as a rating action', () => {
    render(<StarRating value={null} onRate={() => {}} bookTitle="T" />)
    expect(screen.getByRole('button', { name: 'Rate 1 star' })).toBeInTheDocument()
    for (const star of [2, 3, 4, 5]) {
      expect(screen.getByRole('button', { name: `Rate ${star} stars` })).toBeInTheDocument()
    }
  })

  it('reports the tapped star value', () => {
    const onRate = vi.fn()
    render(<StarRating value={null} onRate={onRate} bookTitle="T" />)
    fireEvent.click(screen.getByRole('button', { name: /rate 4 stars/i }))
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
    fireEvent.click(screen.getByRole('button', { name: /rate 5 stars/i }))
    expect(onRate).toHaveBeenCalledWith(5)
    expect(outer).not.toHaveBeenCalled()
  })

  it('pulses the chosen stars when a rating lands, and again on a re-rate', () => {
    const { rerender } = render(<StarRating value={null} onRate={() => {}} bookTitle="T" />)
    // No pulse before any rating is saved.
    expect(document.querySelectorAll('.star-rating__glyph--pulse')).toHaveLength(0)

    // The parent flips `value` after the POST succeeds; the chosen stars pulse.
    rerender(<StarRating value={3} onRate={() => {}} bookTitle="T" />)
    expect(document.querySelectorAll('.star-rating__glyph--pulse')).toHaveLength(3)
    const fourth = screen.getByRole('button', { name: /rate 4 stars/i })
    expect(fourth.querySelector('.star-rating__glyph--pulse')).toBeNull()

    // A later re-rate pulses the new selection (the keyed glyph remounts, so
    // the CSS animation replays even though the class is unchanged).
    rerender(<StarRating value={5} onRate={() => {}} bookTitle="T" />)
    expect(document.querySelectorAll('.star-rating__glyph--pulse')).toHaveLength(5)
  })

  it('does not pulse on first render of an already-rated book', () => {
    render(<StarRating value={4} onRate={() => {}} bookTitle="T" />)
    expect(document.querySelectorAll('.star-rating__glyph--pulse')).toHaveLength(0)
  })
})
