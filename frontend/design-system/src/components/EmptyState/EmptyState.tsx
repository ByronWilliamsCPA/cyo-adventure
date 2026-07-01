import type { ReactNode } from 'react'
import './EmptyState.css'

export interface EmptyStateProps {
  title: string
  description: string
  actions?: ReactNode
  icon?: ReactNode
}

export function EmptyState({ title, description, actions, icon }: EmptyStateProps) {
  return (
    <section className="cyo-empty">
      {icon !== undefined ? (
        <div className="cyo-empty__icon" aria-hidden="true">
          {icon}
        </div>
      ) : null}
      <h2 className="cyo-empty__title">{title}</h2>
      <p className="cyo-empty__description">{description}</p>
      {actions !== undefined ? <div className="cyo-empty__actions">{actions}</div> : null}
    </section>
  )
}
