import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('omits the actions wrapper when actions is a falsy ReactNode', () => {
    render(<EmptyState title="No stories yet" description="Start reading to see it here." actions={false} />)
    expect(document.querySelector('.cyo-empty__actions')).not.toBeInTheDocument()
  })

  it('omits the icon wrapper when icon is a falsy ReactNode', () => {
    render(<EmptyState title="No stories yet" description="Start reading to see it here." icon={0} />)
    expect(document.querySelector('.cyo-empty__icon')).not.toBeInTheDocument()
  })

  it('renders the actions wrapper when actions is a truthy ReactNode', () => {
    render(
      <EmptyState
        title="No stories yet"
        description="Start reading to see it here."
        actions={<button type="button">Browse library</button>}
      />,
    )
    expect(document.querySelector('.cyo-empty__actions')).toBeInTheDocument()
  })
})
