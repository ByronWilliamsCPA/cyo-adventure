import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './Chip.css'

export interface ChipProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type' | 'aria-pressed'> {
  /** Whether the chip is in its toggled-on state. */
  on?: boolean
  children: ReactNode
}

export function Chip({ on = false, className = '', children, ...props }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={on}
      className={`cyo-chip ${on ? 'cyo-chip--on' : ''} ${className}`.trim()}
      {...props}
    >
      {children}
    </button>
  )
}
