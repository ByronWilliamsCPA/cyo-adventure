---
title: "ADR-029: Web accessibility conformance target and testing strategy"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Codify WCAG 2.1 AA as this project's stated web-accessibility target, record the
  two-tier automated testing strategy that already exists in code (per-PR WCAG gate, weekly
  extended scan), and close the gap in which real accessibility engineering existed with no
  standard naming it as a requirement anywhere in the planning docs."
tags:
  - planning
  - architecture
  - decisions
  - accessibility
  - compliance
---

# ADR-029: Web accessibility conformance target and testing strategy

> **Status**: Accepted (2026-08-11)
> **Date**: 2026-08-11
> **Relates to**: [ADR-018](./adr-018-childrens-privacy-compliance.md) (the other
> compliance-shaped ADR in this project; distinct concern, same "name it as a requirement"
> discipline)

## TL;DR

WCAG 2.1 Level AA is this project's stated web-accessibility conformance target, effective now.
The automated testing strategy that already existed in code but nowhere in the planning docs
(axe-core via Playwright, scoped to WCAG tags, gating every PR) is the Tier 1 floor; a new Tier 2
(`A11Y_EXTENDED=1`, WCAG 2.2 plus axe's best-practice rules) runs weekly against `main`, never
per-PR, because the owner ruled the blocking `frontend-e2e` job should not grow in scope or run
time. `eslint-plugin-jsx-a11y` is added at lint time as a third, even-earlier layer. This ADR does
not claim conformance is complete; it names the target, states what already verifies it, and gives
the open gaps a home.

## Context

### Problem

An external prompt (a small-business ADA-lawsuit-risk article) triggered an audit of this
project's web-accessibility posture. The audit found substantial, actively-maintained engineering
already in place: axe-core WCAG scans across every top-level page and modal as a required,
blocking CI check (`frontend/e2e/a11y.spec.ts`); a tested keyboard focus-trap contract citing WCAG
2.1.1 by number (`design-system/src/components/Dialog/Dialog.tsx`,
`frontend/e2e/keyboard-nav.spec.ts`); WCAG 2.5.5 tap-target regression tests; and systematic,
apparently disciplined ARIA/semantic-HTML use across 84 of 92 component files. None of this was
named as a project standard anywhere: CLAUDE.md, `project-vision.md`, `tech-spec.md`, and the
capability register are silent on accessibility, and `roadmap.md`'s Phase 5 line item still reads
as an open, unchecked deliverable ("Performance pass, offline-edge hardening, accessibility (WCAG
AA basics)"). Good practice with no named standard is not durable: it depends on whoever wrote
those tests, not on anything a future contributor, or an auditor, would find documented.

### Constraints

- **Technical**: `@axe-core/playwright` (bundled axe-core 4.12.1) supports WCAG 2.1 and WCAG 2.2
  tags plus a non-normative "best-practice" rule set. `eslint-plugin-jsx-a11y`'s latest release
  (6.10.2) declares a peer range of `eslint@^3..^9`; this project runs `eslint@10.8.0`. The plugin
  is pure AST analysis (`jsx-ast-utils`, `aria-query`, `axobject-query`) with no dependency on
  ESLint's own runtime internals, and its flat-config export (`flatConfigs.recommended`) loaded
  and ran clean end-to-end (`npm run lint`, full tree) once installed; treated as a verified,
  working exception to the peer-range warning rather than an unverified one.
- **Business**: the owner ruled that the per-PR `frontend-e2e` job (currently ~10 minutes,
  required on every PR) must not grow in scope or run time. Any new, broader compliance checking
  goes on a separate, non-blocking, scheduled cadence instead.

### Significance

This is the kind of decision that is cheap to get right now and expensive to reconstruct later:
naming a conformance target and pointing at what verifies it is a few hours of work today, versus
reconstructing "what did we actually test, and when" during an active legal demand letter. The
audit's own conclusion: automated scanning plus a real due-diligence testing history is a
materially stronger position than most ADA Title III defendants have at the time of a claim, but
only if it is documented as a standing practice rather than left as undocumented tribal knowledge.

## Decision

1. **Conformance target**: WCAG 2.1 Level AA. This matches what `frontend/e2e/a11y.spec.ts`
   already gates on (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`) and what
   `docs/testing/coverage-matrix.md` already documents as that suite's scope; this ADR is what
   makes it a stated project requirement rather than an implicit one.
2. **Three-layer testing strategy**, all now named here for the first time:
   - **Lint time**: `eslint-plugin-jsx-a11y`'s recommended flat config, added to
     `frontend/eslint.config.js` alongside the existing `react-hooks`/`react-refresh` plugins.
     Catches missing `alt`, invalid ARIA usage, and non-interactive-elements-with-handlers before
     a PR is even opened. One project-wide rule override,
     `jsx-a11y/no-noninteractive-tabindex` with `roles: ['region']`, accommodates the
     scrollable-region pattern (`tabIndex=0` + `role="region"`) already used in
     `legal/PrivacyPolicyPage.tsx`'s table wrappers, which is the WAI-ARIA APG's own recommended
     technique (SCR26) for a horizontally-scrollable region, not a lint gap.
   - **Tier 1, per-PR (required, unchanged in scope)**: `frontend/e2e/a11y.spec.ts` and
     `frontend/e2e/keyboard-nav.spec.ts`, run by the existing `frontend-e2e` job in `ci.yml`.
     Scoped to WCAG 2.1 A/AA tags only, by design, to stay fast and non-noisy on every PR.
   - **Tier 2, weekly, non-blocking (new)**: the same `a11y.spec.ts` suite, re-run with the new
     `A11Y_EXTENDED=1` environment variable, by the new
     `.github/workflows/accessibility-compliance-weekly.yml`. This widens the axe tag scope to
     WCAG 2.2 A/AA (both `wcag22a` and `wcag22aa` — axe's WCAG tags are additive per level, so
     `wcag22aa` alone would silently skip the 2.2 Level A criteria, the exact pitfall
     `UW-N04` names) plus axe's non-normative "best-practice" rules (missing landmark/heading
     structure, redundant roles, and similar). Deliberately excluded from Tier 1 because
     best-practice findings are not WCAG conformance failures and the owner ruled against growing
     the blocking gate's scope or run time.
3. **Manual verification remains a named, open gap, not a silent one.** Automated scanning (axe
   included) only catches programmatically detectable issues by construction; there is no evidence
   in this repository of a manual screen-reader pass (VoiceOver/NVDA/JAWS), a published
   accessibility statement, or a VPAT/ACR. These are recorded as open work below rather than
   implied to be covered by the two automated tiers.
4. **Skip-links added** to the three persistent-nav shells (`KidShell`, `GuardianShell`,
   `AdminShell`) via a new shared `SkipLink` design-system component
   (`design-system/src/components/SkipLink/`), closing a WCAG 2.4.1 (Bypass Blocks) gap the audit
   found (no "skip to main content" affordance existed anywhere in the app). `LandingPage` was
   deliberately left out: its nav *is* the page's primary content (the kid/guardian door choice),
   not a repeated block to bypass.

## Consequences

### Positive

- Accessibility is now a named, citable project standard instead of undocumented practice; a
  future contributor, or an external auditor, has a document to point to.
- The new Tier 2 scan found real value on its first correct run: four genuine structural gaps
  (tracked as `UW-F27`) invisible to the Tier 1 WCAG-only scan because they are axe best-practice
  rules, not WCAG conformance rules.
- `eslint-plugin-jsx-a11y` moves detection earlier (write time) for a meaningful class of defects
  at effectively zero added CI time (verified: `npm run lint` on the full tree stayed clean and
  fast after enabling it; only 4 real findings surfaced across the whole app, two of them
  already-justified deliberate choices needing only a documented lint exception).

### Trade-offs

- Tier 2's WCAG 2.2 and best-practice coverage is real but non-blocking: a regression there does
  not fail a PR, so it depends on someone reading the weekly run (or its eventual findings landing
  as `UW-*` rows, as `UW-F27` already does) rather than a red PR check forcing immediate attention.
- Naming WCAG 2.1 AA as the target while `roadmap.md` Phase 5 still lists the item as an open
  checkbox is not a contradiction this ADR resolves outright: substantial conformance work exists,
  but full conformance (including the still-open manual-audit gap) is not claimed as complete. See
  Follow-on work.

### Technical debt

- `eslint-plugin-jsx-a11y`'s peer-dependency range does not yet include `eslint@10`; re-verify (or
  drop the implicit exception) on the plugin's next major/minor release that explicitly adds
  ESLint 10 support.
- Tier 2's first run surfaced findings (`UW-F27`) that remain unfixed as of this ADR; Tier 2 exists
  to keep finding drift like this, not to fix it inline.

## Follow-on work

- **`UW-F27`** (Cluster F, phase 5, unscheduled): fix the four structural gaps Tier 2's first
  correct run found (nested `<main>` landmarks on six admin pages, missing `<h1>` on two pages,
  `GuardianLoginPage`'s missing `<main>` landmark, and a heading-order skip on the admin review
  detail page).
- **`UW-N04`** (Cluster N, phase 5, unscheduled, updated by this ADR): WCAG 2.2 scanning now runs,
  but on the new weekly Tier 2 job rather than the per-PR gate. Widening the *blocking* gate itself
  to WCAG 2.2, if ever wanted, is still that row's open work.
- **`UW-F28`** (Cluster F, phase 5, decision): a manual screen-reader audit (VoiceOver + NVDA
  minimum, on the core flows: profile picker, reader, guardian intake, admin review), and a
  published accessibility statement naming the WCAG 2.1 AA target and a contact/remediation path.
  Both wait on an owner ruling (scope/budget for the audit, and what the statement commits to)
  before either is schedulable.
