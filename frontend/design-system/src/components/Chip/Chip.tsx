import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './Chip.css'

export interface ChipProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type' | 'aria-pressed'> {
  /** Whether the chip is in its toggled-on state. */
  on?: boolean
  children: ReactNode
}

/**
 * Toggleable filter/tag chip, rendered as a real button so it is focusable
 * and announces its state via aria-pressed. The type and aria-pressed
 * attributes are set after the props spread so a runtime-supplied value
 * (e.g. through an any-typed spread that bypasses the Omit) cannot
 * override them.
 */
export function Chip({ on = false, className = '', children, ...props }: ChipProps) {
  return (
    <button
      {...props}
      type="button"
      aria-pressed={on}
      className={['cyo-chip', on ? 'cyo-chip--on' : '', className].filter(Boolean).join(' ')}
    >
      {children}
    </button>
  )
}
