import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ProfileFormDialog } from './ProfileFormDialog'

describe('ProfileFormDialog', () => {
  it('explains that a reading-level cap of 99 means no limit', () => {
    render(<ProfileFormDialog title="Add child" onSubmit={vi.fn()} onClose={vi.fn()} />)

    const cap = screen.getByLabelText(/reading level cap/i)
    const helpId = cap.getAttribute('aria-describedby')
    expect(helpId).toBeTruthy()

    const help = helpId ? document.getElementById(helpId) : null
    expect(help).not.toBeNull()
    expect(help).toHaveTextContent(/99.*no limit/i)
  })
})
