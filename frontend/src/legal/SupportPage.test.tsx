import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { CONTACT_EMAIL } from './legalContact'
import { SupportPage } from './SupportPage'

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/support']}>
      <Routes>
        <Route path="/support" element={<SupportPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('SupportPage', () => {
  it('renders without any auth provider mounted', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/support/i)
  })

  it('leads with a contact route matching the shared constant', () => {
    renderPage()
    const link = screen.getByRole('link', { name: CONTACT_EMAIL })
    expect(link).toHaveAttribute('href', `mailto:${CONTACT_EMAIL}`)
  })

  it('collects nothing at all', () => {
    // #CRITICAL anchor: a parent reaches this page mid-verification, having
    // just been asked for a payment card. That is precisely the context a
    // phishing page imitates. A support page that grows a "contact form" would
    // train parents that entering details on our pages after a card prompt is
    // normal, so the page stays input-free and this test is what keeps it that
    // way. Query the container directly: an <input> with no accessible name is
    // invisible to getAllByRole, which would make a role-based assertion pass
    // over exactly the element it is meant to catch.
    const { container } = renderPage()
    expect(container.querySelectorAll('input')).toHaveLength(0)
    expect(container.querySelectorAll('textarea')).toHaveLength(0)
    expect(container.querySelectorAll('select')).toHaveLength(0)
    expect(container.querySelectorAll('form')).toHaveLength(0)
  })

  it('says we never see the card number', () => {
    renderPage()
    expect(screen.getByText(/we never see the number/i)).toBeInTheDocument()
  })

  it('names no currency amount for the verification charge', () => {
    // Runbook Q2 is unanswered as of 2026-08-10: whether Epic's card method
    // captures and refunds or authorises only, and how it is labelled, is not
    // established. Any figure here would be invented, and a parent would
    // reconcile it against a statement. Fails if a digit ever appears next to a
    // currency symbol anywhere on the page.
    const { container } = renderPage()
    expect(container.textContent ?? '').not.toMatch(/[$£€]\s?\d/)
  })

  it('tells guardians not to send us a child real name or birthday', () => {
    renderPage()
    expect(screen.getByText(/do not send us your child/i)).toBeInTheDocument()
  })
})
