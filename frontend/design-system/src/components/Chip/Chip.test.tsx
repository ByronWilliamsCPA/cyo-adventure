import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Chip } from './Chip'

describe('Chip', () => {
  it('renders the children as the chip label', () => {
    render(<Chip>Gentle</Chip>)
    expect(screen.getByText('Gentle')).toBeInTheDocument()
  })

  it('defaults to off: aria-pressed=false and no "on" modifier class', () => {
    render(<Chip>Gentle</Chip>)
    const chip = screen.getByRole('button', { name: 'Gentle' })
    expect(chip).toHaveAttribute('aria-pressed', 'false')
    expect(chip.className).not.toContain('cyo-chip--on')
  })

  it('reflects on=true via aria-pressed and the "on" modifier class', () => {
    render(<Chip on>Gentle</Chip>)
    const chip = screen.getByRole('button', { name: 'Gentle' })
    expect(chip).toHaveAttribute('aria-pressed', 'true')
    expect(chip.className).toContain('cyo-chip--on')
  })

  it('always renders type="button" regardless of spread props', () => {
    render(<Chip>Gentle</Chip>)
    expect(screen.getByRole('button', { name: 'Gentle' })).toHaveAttribute('type', 'button')
  })

  it('forwards onClick and other button props', () => {
    const onClick = vi.fn()
    render(<Chip onClick={onClick}>Gentle</Chip>)
    fireEvent.click(screen.getByRole('button', { name: 'Gentle' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
