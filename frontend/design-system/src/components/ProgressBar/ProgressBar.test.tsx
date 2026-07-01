import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProgressBar } from './ProgressBar'

describe('ProgressBar', () => {
  it('clamps a valid value into the 0-100 range', () => {
    render(<ProgressBar value={150} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
  })

  it('falls back to 0 instead of propagating NaN', () => {
    render(<ProgressBar value={NaN} />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '0')
    expect(bar).toHaveAttribute('aria-label', '0% complete')
  })

  it('falls back to 0 instead of propagating Infinity', () => {
    render(<ProgressBar value={Infinity} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
  })

  it('renders a visible label span when showLabel is true', () => {
    render(<ProgressBar value={50} showLabel />)
    expect(screen.getByText('50% complete')).toBeInTheDocument()
  })

  it('omits the visible label span when showLabel is false', () => {
    render(<ProgressBar value={50} />)
    expect(document.querySelector('.cyo-progress__label')).not.toBeInTheDocument()
  })

  it('uses a custom label over the computed percentage text', () => {
    render(<ProgressBar value={50} showLabel label="Halfway there" />)
    expect(screen.getByText('Halfway there')).toBeInTheDocument()
  })
})
