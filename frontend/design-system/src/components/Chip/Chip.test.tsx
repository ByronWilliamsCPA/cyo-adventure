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

  it('always renders type="button" and its own aria-pressed even when spread props conflict', () => {
    // Simulates an any-typed spread that bypasses the Omit at the type layer.
    const conflicting = { type: 'submit', 'aria-pressed': true } as unknown as Partial<
      Parameters<typeof Chip>[0]
    >
    render(<Chip {...conflicting}>Gentle</Chip>)
    const chip = screen.getByRole('button', { name: 'Gentle' })
    expect(chip).toHaveAttribute('type', 'button')
    expect(chip).toHaveAttribute('aria-pressed', 'false')
  })

  it('forwards onClick and other button props', () => {
    const onClick = vi.fn()
    render(<Chip onClick={onClick}>Gentle</Chip>)
    fireEvent.click(screen.getByRole('button', { name: 'Gentle' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('is keyboard-reachable: a real button that takes focus', () => {
    render(<Chip>Gentle</Chip>)
    const chip = screen.getByRole('button', { name: 'Gentle' })
    chip.focus()
    expect(chip).toHaveFocus()
  })

  it('does not fire onClick when disabled', () => {
    const onClick = vi.fn()
    render(
      <Chip disabled onClick={onClick}>
        Gentle
      </Chip>,
    )
    const chip = screen.getByRole('button', { name: 'Gentle' })
    expect(chip).toBeDisabled()
    fireEvent.click(chip)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('tolerates a click with no onClick handler', () => {
    render(<Chip>Gentle</Chip>)
    expect(() => fireEvent.click(screen.getByRole('button', { name: 'Gentle' }))).not.toThrow()
  })
})
