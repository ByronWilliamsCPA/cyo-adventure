import type { HTMLAttributes, ReactNode } from 'react'
import './Card.css'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /**
   * Adds a hover-lift shadow and focus-within lift, for a card whose whole
   * area is one click target. Styling only: Card renders a plain div, so
   * the click target must be a focusable element inside it (a Link or
   * button); an onClick on the Card itself would be mouse-only and
   * keyboard-unreachable. Do not set it on a card that merely hosts its own
   * controls with their own hover/focus states.
   */
  interactive?: boolean
  children: ReactNode
}

/**
 * Raised-card container for list rows and panels.
 *
 * The classes (`cyo-card`, `cyo-card--interactive`) are also usable as raw
 * class names (Card.css is imported globally by the app's index.css), so
 * existing markup (`li`, `article`) can adopt the same look without
 * restructuring; the guardian console currently consumes them that way.
 */
export function Card({ interactive = false, className = '', children, ...props }: CardProps) {
  return (
    <div
      className={['cyo-card', interactive ? 'cyo-card--interactive' : '', className]
        .filter(Boolean)
        .join(' ')}
      {...props}
    >
      {children}
    </div>
  )
}
