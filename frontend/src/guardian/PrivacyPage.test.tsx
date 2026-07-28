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

  it('states the no-retention, no-training posture G11 asks for, and scopes it', () => {
    // The guardrail behind this sentence is a ROUTING control on one vendor's
    // workspace (ADR-003's 2026-07-28 amendment). generation_provider still
    // admits "anthropic", a direct adapter that bypasses the route entirely,
    // and cover art goes elsewhere again. Claiming it of "the services that
    // write our stories" generally was an overclaim, so the scoping sentence
    // is pinned alongside the posture: dropping it re-creates the overclaim.
    renderPage()
    expect(screen.getByText(/not used to train models/i)).toBeInTheDocument()
    expect(
      screen.getByText(/an administrator can send story writing to a writing/i)
    ).toBeInTheDocument()
  })

  it('says the premise it sends includes the words the requester typed', () => {
    // brief.py:197 is `premise=request.request_text`, and prompts.py serialises
    // that brief into the provider prompt. An earlier draft listed the settings
    // (age band, reading level, caps, banned themes) as the whole payload,
    // which made the page false by omission about its most sensitive egress.
    renderPage()
    expect(screen.getByText(/exactly as they were typed/i)).toBeInTheDocument()
    expect(
      screen.getByText(/approving a request is what sends your child's own sentence/i)
    ).toBeInTheDocument()
  })

  it('splits erasure by route rather than promising profile deletion erases the text', () => {
    // api/profiles.py::delete_profile de-links story requests (profile_id set
    // null) rather than deleting them; only DELETE /v1/me/family erases the
    // text. This is a GDPR Art. 17 / COPPA 312.10 statement, so the two routes
    // must not be collapsed back into one sentence.
    renderPage()
    expect(screen.getByText(/erased when you delete your family account/i)).toBeInTheDocument()
  })

  it('describes family-only as the default rather than promising it is permanent', () => {
    // api/approval.py lets an approver publish to the shared catalog, so an
    // absolute "never shared" claim would be false. Guard the hedge.
    renderPage()
    expect(screen.getByText(/stays with your family by default/i)).toBeInTheDocument()
  })

  it('links to the guardian controls it tells the reader they have', () => {
    renderPage()
    // Two bullets now point at Profiles (settings, and profile deletion), so
    // this asserts over all of them rather than assuming a single match.
    const profileLinks = screen.getAllByRole('link', { name: /profiles/i })
    expect(profileLinks.length).toBeGreaterThan(0)
    for (const link of profileLinks) {
      expect(link).toHaveAttribute('href', '/guardian/profiles')
    }
    expect(screen.getByRole('link', { name: /requests from your kids/i })).toHaveAttribute(
      'href',
      '/guardian/requests'
    )
    expect(screen.getByRole('link', { name: /books/i })).toHaveAttribute('href', '/guardian/books')
  })

  it('does not promise a family-deletion control the app has no surface for', () => {
    // DELETE /v1/me/family exists and is in the generated client, but nothing
    // under frontend/src outside src/client/ calls it, and capability-register
    // G12 is still partial. Every other bullet links to a live surface; this
    // one must keep saying it does not, until the deletion UI ships.
    renderPage()
    expect(screen.getByText(/no button for this in the app yet/i)).toBeInTheDocument()
  })

  it('keeps the deliberate-nots list announced as a list', () => {
    // .privacy__nots sets list-style: none, which drops list semantics in
    // Safari/VoiceOver. The explicit role="list" is what restores them.
    renderPage()
    const nots = screen.getAllByRole('list').find((el) => el.classList.contains('privacy__nots'))
    expect(nots).toBeDefined()
    expect(nots).toHaveAttribute('role', 'list')
  })
})
