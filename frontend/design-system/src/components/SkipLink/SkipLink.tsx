import type { ReactNode } from 'react'
import './SkipLink.css'

export interface SkipLinkProps {
  /** id of the landmark to jump to (typically the shell's <main>). */
  targetId: string
  children?: ReactNode
  className?: string
}

/**
 * Standard "skip to main content" link (WCAG 2.4.1 Bypass Blocks): hidden
 * off-screen until it receives keyboard focus, so a screen-reader or
 * keyboard-only user can bypass a shell's persistent nav without changing
 * anything for a mouse/touch user. Must be the first focusable element in
 * the shell, and `targetId` must resolve to a focusable landmark (e.g. a
 * <main tabIndex={-1}>) so focus actually lands there on activation.
 */
export function SkipLink({
  targetId,
  children = 'Skip to main content',
  className = '',
}: SkipLinkProps) {
  return (
    <a href={`#${targetId}`} className={['cyo-skip-link', className].filter(Boolean).join(' ')}>
      {children}
    </a>
  )
}
