import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { LandingPage } from './LandingPage'

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>
  )
}

describe('LandingPage', () => {
  it('shows the kid door linking to the profile picker', () => {
    renderLanding()
    const kidDoor = screen.getByRole('link', { name: /kids/i })
    expect(kidDoor).toHaveAttribute('href', '/kids')
  })

  it('shows the grown-up door linking to the guardian console with the admin note', () => {
    renderLanding()
    const guardianDoor = screen.getByRole('link', { name: /grown-ups/i })
    expect(guardianDoor).toHaveAttribute('href', '/guardian')
    expect(guardianDoor).toHaveTextContent('Admins sign in here too')
  })

  it('names the app', () => {
    renderLanding()
    expect(screen.getByRole('heading', { level: 1, name: 'CYO Adventure' })).toBeInTheDocument()
  })
})
