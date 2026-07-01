import './ProgressBar.css'

export interface ProgressBarProps {
  value: number
  label?: string
  showLabel?: boolean
}

export function ProgressBar({ value, label, showLabel = false }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value))
  const ariaLabel = label ?? `${Math.round(clamped)}% complete`

  return (
    <div className="cyo-progress">
      <div
        className="cyo-progress__track"
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={ariaLabel}
      >
        <div
          className="cyo-progress__fill"
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showLabel ? (
        <span className="cyo-progress__label" aria-hidden="true">
          {ariaLabel}
        </span>
      ) : null}
    </div>
  )
}
