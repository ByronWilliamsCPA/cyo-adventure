import type { ReactNode } from 'react'
import './LoadingStatus.css'

export interface LoadingStatusProps {
  children?: ReactNode
  className?: string
}

/**
 * Shared loading indicator: a `role="status"`/`aria-live="polite"` region
 * announced to assistive tech while data is in flight. Pass `className` to
 * carry over a call site's positioning class (e.g. a fixed-position route
 * fallback); it is space-joined alongside the component's own base class so
 * both sets of styles apply.
 */
export function LoadingStatus({ children, className = '' }: LoadingStatusProps) {
  return (
    <div role="status" aria-live="polite" className={['cyo-loading', className].filter(Boolean).join(' ')}>
      {children ?? 'Loading…'}
    </div>
  )
}
