import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { CONTACT_EMAIL } from './legalContact'
import { PrivacyPolicyPage } from './PrivacyPolicyPage'

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/privacy']}>
      <Routes>
        <Route path="/privacy" element={<PrivacyPolicyPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('PrivacyPolicyPage', () => {
  it('renders without any auth provider mounted', () => {
    // The whole point of this page is that a signed-out visitor, arriving from
    // Epic's KWS verification screens, can read it. Rendering it here with no
    // AuthProvider, no session, and no device grant is the test of that: if a
    // future edit reaches for useAuth or a data hook, this fails immediately
    // rather than at the moment a real parent follows the registered URL.
    renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      /cyo adventure privacy policy/i
    )
  })

  it('publishes a working contact route matching the shared constant', () => {
    renderPage()
    const links = screen.getAllByRole('link', { name: CONTACT_EMAIL })
    expect(links.length).toBeGreaterThan(0)
    for (const link of links) {
      expect(link).toHaveAttribute('href', `mailto:${CONTACT_EMAIL}`)
    }
  })

  it('states plainly what is never collected from a child', () => {
    renderPage()
    expect(screen.getByText(/never collect from a child/i)).toBeInTheDocument()
  })

  it('names Epic as a recipient of a parent email for verification', () => {
    // A recipient table that omits the verification vendor would be false by
    // omission about the one egress a parent is most likely to ask about,
    // since they meet it face-on during the KWS flow.
    // getAllByText, not getByText: the vendor is named twice on purpose, once
    // in the consent section describing what is coming and once in the
    // recipient table. A single-match assertion here would fail for the wrong
    // reason and invite someone to "fix" it by deleting one of the mentions.
    renderPage()
    expect(screen.getAllByText(/kids web services/i).length).toBeGreaterThan(0)
  })

  describe('claims deliberately withheld pending counsel or unfinished work', () => {
    // Each absence below is required by PrivacyPolicyPage's #CRITICAL block and
    // traces to a specific "do not publish this yet" in
    // docs/compliance/privacy-notice.md. These assertions are worded as
    // absences on purpose: they fail when someone re-adds the claim, which is
    // the direction the risk runs. Deleting one of these tests to make an edit
    // pass is the failure mode; the claim has to become TRUE first.

    it('does not assert a per-purpose GDPR legal basis', () => {
      // Draft Note 1: the Article 6 bases are not counsel-reviewed.
      renderPage()
      expect(screen.queryByText(/legal basis/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/legitimate interest/i)).not.toBeInTheDocument()
    })

    it('does not assert that processors may not use data for their own purposes', () => {
      // processor-dpa-checklist.md: several DPAs are unexecuted, so the
      // processor-only claim has nothing behind it for those vendors yet.
      renderPage()
      expect(screen.queryByText(/their own purposes/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/acts on our instructions only/i)).not.toBeInTheDocument()
    })

    it('does not name an international transfer mechanism', () => {
      // coppa-gdpr-remediation-plan.md Phase 5: neither SCCs nor a DPF
      // self-certification is executed. Naming one would represent paperwork
      // that does not exist.
      renderPage()
      expect(screen.queryByText(/standard contractual clauses/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/data privacy framework/i)).not.toBeInTheDocument()
    })

    it('does not promise re-consent on a material change', () => {
      // The re-consent-on-change flow is Phase 2b and is not built. The page
      // describes contacting the account email instead, which is what actually
      // happens today.
      renderPage()
      expect(screen.queryByText(/re-confirm your consent/i)).not.toBeInTheDocument()
      expect(
        screen.getByText(/contact you at the email address on your account/i)
      ).toBeInTheDocument()
    })
  })
})
