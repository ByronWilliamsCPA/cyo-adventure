import type { HTMLAttributes, ReactNode } from 'react'
import './Card.css'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Adds a hover-lift shadow, for a card that is itself a whole clickable row. */
  interactive?: boolean
  children: ReactNode
}

export function Card({ interactive = false, className = '', children, ...props }: CardProps) {
  return (
    <div
      className={`cyo-card ${interactive ? 'cyo-card--interactive' : ''} ${className}`.trim()}
      {...props}
    >
      {children}
    </div>
  )
}
