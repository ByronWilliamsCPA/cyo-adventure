import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChoiceButton } from './ChoiceButton'

describe('ChoiceButton', () => {
  it('renders the label', () => {
    render(<ChoiceButton label="Take the left path" />)
    expect(screen.getByText('Take the left path')).toBeInTheDocument()
  })

  it('defaults to unselected: aria-pressed=false and no selected modifier class', () => {
    render(<ChoiceButton label="Take the left path" />)
    const button = screen.getByRole('button', { name: 'Take the left path' })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(button.className).not.toContain('cyo-choice--selected')
  })

  it('reflects selected=true via aria-pressed and the selected modifier class', () => {
    render(<ChoiceButton label="Take the left path" selected />)
    const button = screen.getByRole('button', { name: 'Take the left path' })
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(button.className).toContain('cyo-choice--selected')
  })

  it('always renders type="button" regardless of spread props', () => {
    render(<ChoiceButton label="Take the left path" />)
    expect(screen.getByRole('button', { name: 'Take the left path' })).toHaveAttribute(
      'type',
      'button',
    )
  })

  it('forwards onClick and other button props', () => {
    const onClick = vi.fn()
    render(<ChoiceButton label="Take the left path" onClick={onClick} />)
    fireEvent.click(screen.getByRole('button', { name: 'Take the left path' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
