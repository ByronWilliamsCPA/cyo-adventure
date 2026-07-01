import type { ButtonHTMLAttributes } from 'react'
import './ChoiceButton.css'

export interface ChoiceButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type' | 'aria-pressed'> {
  label: string
  selected?: boolean
}

export function ChoiceButton({
  label,
  selected = false,
  className = '',
  ...props
}: ChoiceButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={`cyo-choice ${selected ? 'cyo-choice--selected' : ''} ${className}`.trim()}
      {...props}
    >
      <span className="cyo-choice__marker" aria-hidden="true">
        ›
      </span>
      <span className="cyo-choice__label">{label}</span>
    </button>
  )
}
