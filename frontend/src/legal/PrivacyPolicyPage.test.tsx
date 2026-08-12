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

  describe('claims that must stay, because the code is narrower than the obvious wording', () => {
    // The mirror image of the withheld-claims block below. Each assertion here
    // guards a sentence that reads like an awkward hedge and is exactly what an
    // editor tidies away; the hedge is the accurate version, and the tidy one
    // is false. PrivacyPolicyPage's docstring names the source for each.

    it('says the PII check stops the request, and never that it removes anything', () => {
      // generation/pii.py::assert_prompt_pii_safe RAISES ValidationError and
      // fails the job. It strips nothing. guardian/PrivacyPage.tsx carries a
      // standing instruction that the wording "must not imply that it does",
      // and "checked first to remove" is the phrasing that instruction forbids.
      renderPage()
      const promptCell = screen.getByText(/stops the request rather than editing it/i)
      // Scoped to the cell making the claim, not the whole page: a document-wide
      // /remove/ ban also catches the retention row's "when we remove them by
      // hand", which is a legitimate and unrelated use of the word.
      expect(promptCell.textContent).not.toMatch(/remove|strip|redact|scrub|filter out/i)
      expect(screen.queryByText(/checked first to remove/i)).not.toBeInTheDocument()
    })

    it('admits the PII check cannot catch every name', () => {
      // The guard matches registered child display names plus email, US-phone,
      // and street-shaped patterns. A friend's name, an unregistered sibling, a
      // school or a city passes through, so an unqualified claim would be false.
      renderPage()
      expect(screen.getByText(/cannot catch every name a child might type/i)).toBeInTheDocument()
    })

    it('discloses the guardian country code and language sent to Epic, not the email alone', () => {
      // consent/kws_client.py sends {email, location, language, ...}. An
      // email-only row understates the transfer, so the row must name the
      // country and the language too.
      //
      // The row said "for the child" until 2026-08-12, on the strength of a
      // kws_client.py docstring that claimed the field carried the child's
      // location. The code never did that: api/consent.py passes body.location
      // straight through from the country the GUARDIAN picks on the
      // verification screen, and no screen asks for a child's country at all.
      // Asserting "for their own account" rather than "for the child" is what
      // keeps a wrong docstring from re-entering the published policy, which is
      // exactly the route it took the first time.
      renderPage()
      expect(
        screen.getByText(/country or region code that parent selected for their own account/i)
      ).toBeInTheDocument()
      expect(screen.queryByText(/country or region code for the child/i)).not.toBeInTheDocument()
    })

    it('reconciles the never-collect list with that country code', () => {
      // The list must not flatly deny collecting "location" while the
      // verification step sends a country code. It says "precise location"
      // instead, and then names the one exception rather than leaving a reader
      // to discover it in the recipient table.
      renderPage()
      expect(screen.getByText(/do not collect a child's precise location/i)).toBeInTheDocument()
    })

    it('discloses that an AgeGraph match can skip verification entirely', () => {
      // core/config.py's kws_enabled_methods note: a matched hashed email
      // pre-verifies a parent with no new verification event on our side, under
      // a method the parent-verified webhook never reports back.
      renderPage()
      expect(screen.getByText(/without sending you anything/i)).toBeInTheDocument()
      expect(screen.getByText(/does not tell us which method was used/i)).toBeInTheDocument()
    })

    it('discloses that Epic is not acting solely on our instructions', () => {
      // ADR-018 records KWS as an independent controller of AgeGraph data that
      // reuses the parent email hash to serve its other customers.
      // Deliberately NOT the inverse of the withheld processor-only claim
      // below: both can be true of different vendors, so they are pinned apart.
      renderPage()
      expect(screen.getAllByText(/not acting solely on our instructions/i).length).toBeGreaterThan(
        0
      )
    })

    it.each([
      ['export', /no button for this in the app yet/i],
      ['whole-family deletion', /deleting your whole family account is done by email/i],
      ['pause', /this is done by email too/i],
    ])('describes %s as an email request rather than an app control', (_label, pattern) => {
      // Only profile edit and profile delete are wired. DELETE /v1/me/family
      // exists in the generated client but nothing under frontend/src outside
      // src/client/ calls it, and capability-register G12 is still partial.
      // guardian/PrivacyPage.test.tsx pins "no button for this in the app yet"
      // on the signed-in page; a public page promising the button would
      // contradict a named regression test one directory over.
      renderPage()
      expect(screen.getByText(pattern)).toBeInTheDocument()
    })
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
