import './StatusBadge.css'

export type StatusBadgeStatus = 'connected' | 'offline' | 'loading' | 'error'

const DEFAULT_LABELS: Record<StatusBadgeStatus, string> = {
  connected: 'Connected',
  offline: 'Offline',
  loading: 'Connecting…',
  error: 'Error',
}

export interface StatusBadgeProps {
  status: StatusBadgeStatus
  label?: string
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const displayLabel = label ?? DEFAULT_LABELS[status]
  return (
    <span
      className={`cyo-status cyo-status--${status}`}
      role="status"
      aria-label={displayLabel}
    >
      <span className="cyo-status__dot" aria-hidden="true" />
      <span className="cyo-status__label">{displayLabel}</span>
    </span>
  )
}
