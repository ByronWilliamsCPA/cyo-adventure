import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { WeeklyRing } from './WeeklyRing'

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  cleanup()
})

describe('WeeklyRing', () => {
  it('announces the day count and goal via an accessible label', () => {
    render(<WeeklyRing profileId="p1" daysReadThisWeek={2} goalDays={3} reduceMotion={false} />)
    expect(screen.getByRole('img', { name: 'You read on 2 days this week, out of a goal of 3' })).toBeInTheDocument()
  })

  it('uses singular framing for exactly one day', () => {
    render(<WeeklyRing profileId="p1" daysReadThisWeek={1} goalDays={3} reduceMotion={false} />)
    expect(screen.getByRole('img', { name: 'You read on 1 day this week, out of a goal of 3' })).toBeInTheDocument()
  })

  it('shows the day count as plain text, never minutes', () => {
    render(<WeeklyRing profileId="p1" daysReadThisWeek={2} goalDays={3} reduceMotion={false} />)
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.queryByText(/minute/i)).toBeNull()
  })

  it('clamps an over-goal day count instead of over-filling the ring', () => {
    render(<WeeklyRing profileId="p1" daysReadThisWeek={9} goalDays={3} reduceMotion={false} />)
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('never renders negative or reminder copy at any fill level', () => {
    for (const days of [0, 1, 2, 3]) {
      cleanup()
      render(<WeeklyRing profileId="p1" daysReadThisWeek={days} goalDays={3} reduceMotion={false} />)
      expect(screen.queryByText(/miss|lost|reset|remind|almost|left|more day/i)).toBeNull()
    }
  })

  it('celebrates once when the ring fills, and not again on a re-render the same week', () => {
    const fixedNow = () => new Date(2026, 0, 7) // a Wednesday
    const { rerender } = render(
      <WeeklyRing profileId="p1" daysReadThisWeek={3} goalDays={3} reduceMotion={false} now={fixedNow} />
    )
    expect(screen.getByTestId('weekly-ring')).toHaveClass('weekly-ring--celebrate')

    cleanup()
    render(
      <WeeklyRing profileId="p1" daysReadThisWeek={3} goalDays={3} reduceMotion={false} now={fixedNow} />
    )
    expect(screen.getByTestId('weekly-ring')).not.toHaveClass('weekly-ring--celebrate')
    // rerender is unused beyond exercising the render path above.
    void rerender
  })

  it('does not celebrate while the ring is unfilled', () => {
    render(<WeeklyRing profileId="p1" daysReadThisWeek={2} goalDays={3} reduceMotion={false} />)
    expect(screen.getByTestId('weekly-ring')).not.toHaveClass('weekly-ring--celebrate')
  })

  it('suppresses the celebration animation class under reduce-motion, even when filled', () => {
    render(
      <WeeklyRing profileId="p1" daysReadThisWeek={3} goalDays={3} reduceMotion now={() => new Date(2026, 0, 8)} />
    )
    expect(screen.getByTestId('weekly-ring')).not.toHaveClass('weekly-ring--celebrate')
  })

  it('celebrates again in a new week after a prior week already celebrated', () => {
    render(
      <WeeklyRing
        profileId="p1"
        daysReadThisWeek={3}
        goalDays={3}
        reduceMotion={false}
        now={() => new Date(2026, 0, 5)} // week 1
      />
    )
    expect(screen.getByTestId('weekly-ring')).toHaveClass('weekly-ring--celebrate')

    cleanup()
    render(
      <WeeklyRing
        profileId="p1"
        daysReadThisWeek={3}
        goalDays={3}
        reduceMotion={false}
        now={() => new Date(2026, 0, 12)} // week 2
      />
    )
    expect(screen.getByTestId('weekly-ring')).toHaveClass('weekly-ring--celebrate')
  })

  it('scopes celebration state per profile', () => {
    const fixedNow = () => new Date(2026, 0, 7)
    render(
      <WeeklyRing profileId="sibling-a" daysReadThisWeek={3} goalDays={3} reduceMotion={false} now={fixedNow} />
    )
    cleanup()
    render(
      <WeeklyRing profileId="sibling-b" daysReadThisWeek={3} goalDays={3} reduceMotion={false} now={fixedNow} />
    )
    expect(screen.getByTestId('weekly-ring')).toHaveClass('weekly-ring--celebrate')
  })
})
