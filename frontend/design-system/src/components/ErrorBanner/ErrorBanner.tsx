import type { ReactNode } from 'react'
import { Button } from '../Button'
import './ErrorBanner.css'

export interface ErrorBannerProps {
  children: ReactNode
  onRetry?: () => void
  retryLabel?: string
  className?: string
}

export function ErrorBanner({ children, onRetry, retryLabel = 'Try again', className }: ErrorBannerProps) {
  return (
    <div role="alert" className={['cyo-error', className].filter(Boolean).join(' ')}>
      {children}
      {onRetry ? (
        <Button variant="primary" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </div>
  )
}
