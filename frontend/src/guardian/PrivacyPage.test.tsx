import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { PrivacyPage } from './PrivacyPage'

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/guardian/privacy']}>
      <Routes>
        <Route path="/guardian/privacy" element={<PrivacyPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('PrivacyPage', () => {
  it('renders a single page heading and the section structure beneath it', () => {
    renderPage()
    const headings = screen.getAllByRole('heading', { level: 1 })
    expect(headings).toHaveLength(1)
    expect(headings[0]).toHaveTextContent(/how we handle your family's data/i)
    // Every other section is an h2, so the page has no heading-level gaps for
    // a screen-reader user navigating by landmark.
    expect(screen.getAllByRole('heading', { level: 2 }).length).toBeGreaterThan(5)
  })

  it('disclaims being the legal privacy notice', () => {
    // The page is a plain-language explanation; the statutory notice is a
    // separate Phase 7 deliverable (ADR-018 D4). If this disclaimer is ever
    // dropped, the page starts reading as the legal document it is not.
    renderPage()
    expect(screen.getByText(/not the legal privacy notice/i)).toBeInTheDocument()
  })

  it('states that an identifying request fails rather than continuing silently', () => {
    // assert_prompt_pii_safe RAISES and fails the job; it does not redact.
    // A future edit softening this into "we remove personal details" would
    // make the page describe a system we deliberately did not build.
    renderPage()
    expect(screen.getByText(/stops with an error rather than carrying on/i)).toBeInTheDocument()
  })

  it('discloses that a kid-typed request reaches outside safety services', () => {
    // This is the one real egress of child-typed words, and burying it is the
    // failure mode this page exists to avoid. Pinned so it cannot quietly go.
    renderPage()
    expect(
      screen.getByText(/checked for unsafe content by outside safety services/i)
    ).toBeInTheDocument()
  })

  it('says plainly that the stories are AI-written and are reviewed by a person', () => {
    // G11 asks for "where the AI text came from" and "who reviewed it". A
    // privacy page for an AI product that never mentions the AI is the exact
    // omission this row exists to prevent.
    renderPage()
    expect(screen.getByText(/written by an AI writing model/i)).toBeInTheDocument()
    expect(screen.getByText(/a person reviews it and has to approve it/i)).toBeInTheDocument()
  })

  it('states the no-retention, no-training posture G11 asks for', () => {
    renderPage()
    expect(screen.getByText(/not used to train their models/i)).toBeInTheDocument()
  })

  it('describes family-only as the default rather than promising it is permanent', () => {
    // api/approval.py lets an approver publish to the shared catalog, so an
    // absolute "never shared" claim would be false. Guard the hedge.
    renderPage()
    expect(screen.getByText(/stays with your family by default/i)).toBeInTheDocument()
  })

  it('links to the guardian controls it tells the reader they have', () => {
    renderPage()
    expect(screen.getByRole('link', { name: /profiles/i })).toHaveAttribute(
      'href',
      '/guardian/profiles'
    )
    expect(screen.getByRole('link', { name: /requests from your kids/i })).toHaveAttribute(
      'href',
      '/guardian/requests'
    )
    expect(screen.getByRole('link', { name: /books/i })).toHaveAttribute('href', '/guardian/books')
  })
})
