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
already in place: axe-core WCAG scans as a required, blocking CI check
(`frontend/e2e/a11y.spec.ts`); a tested keyboard focus-trap contract citing WCAG 2.1.1 by number
(`design-system/src/components/Dialog/Dialog.tsx`, `frontend/e2e/keyboard-nav.spec.ts`); WCAG
2.5.5 tap-target regression tests; and widespread ARIA/semantic-HTML use (`grep -lE
'aria-[a-z]+=|role="|<button|<label|htmlFor=' -r src --include='*.tsx' | grep -v
'\.test\.tsx$' | wc -l` finds 69 of 92 non-test component files, a lower bound: the pattern is
narrow by design so the count stays honestly reproducible rather than impressive). None of this
was named as a project standard anywhere: CLAUDE.md, `project-vision.md`, `tech-spec.md`, and the
capability register are silent on accessibility, and `roadmap.md`'s Phase 5 line item still reads
as an open, unchecked deliverable ("Performance pass, offline-edge hardening, accessibility (WCAG
AA basics)"). Good practice with no named standard is not durable: it depends on whoever wrote
those tests, not on anything a future contributor, or an auditor, would find documented.

**The axe-core scan's own coverage is narrower than "every page" and needs stating precisely,
since overstating it in the one document meant to be citable evidence is worse than saying
nothing.** `a11y.spec.ts` visits 15 distinct routes. Cross-referenced against `router.tsx`, 11
routes are scanned at neither tier: `/admin/library`, `/admin/users`, `/admin/audit`,
`/guardian/review/:storybookId`, `/guardian/reading`, `/guardian/connections`,
`/guardian/devices`, `/guardian/privacy`, `/guardian/preview/:profileId`, `/privacy`, and
`/support`. Two of those are pages this very PR edits for accessibility:
`legal/PrivacyPolicyPage.tsx` (the `role="region"` scrollable-table pattern motivating the
project-wide lint override below) and `guardian/PrivacyPage.tsx` (the `role="list"`
suppression), and neither has ever been axe-scanned. Closing this gap is `UW-F29` below.

### Constraints

- **Technical**: `@axe-core/playwright` (bundled axe-core 4.12.1) supports WCAG 2.1 and WCAG 2.2
  tags plus a non-normative "best-practice" rule set. `eslint-plugin-jsx-a11y`'s latest release
  (6.10.2) declares a peer range of `eslint@^3..^9`; this project runs `eslint@10.8.0`. This is
  the exact precondition that `UW-I06`/remediation-plan `P14` deferred the plugin on
  (2026-07-17); it is still unmet upstream, and shipping anyway reproduced the named risk once
  before landing: a first attempt installed the plugin with `npm install --force`, which
  succeeded locally but produced a lockfile that a plain `npm ci` (what every CI job actually
  runs) rejected with `ERESOLVE`, breaking every frontend job on this PR's first push. The fix,
  not a workaround: a `package.json` `overrides` entry
  (`"eslint-plugin-jsx-a11y": { "eslint": "$eslint" }`) that pins the plugin's peer check to this
  project's own resolved `eslint` version. The plugin is pure AST analysis (`jsx-ast-utils`,
  `aria-query`, `axobject-query`) with no dependency on ESLint's own runtime internals, and its
  flat-config export (`flatConfigs.recommended`) ran clean end-to-end (`npm run lint`, full tree,
  and a clean `npm ci` from the regenerated lockfile) once the override was in place. This
  override is a **permanent** peer-check silence, not a temporary one: unlike this project's other
  `overrides` entries (which bump a transitive package past a known CVE and are self-evidently
  temporary), this one removes the signal that would otherwise prompt revisiting it. See
  Technical debt.
- **Business**: the per-PR `frontend-e2e` job is measured, not estimated: this PR's own run took
  3m58s (`Frontend E2E (Playwright, mocked tier)`, 2026-08-11). **Ruling (2026-08-11, this PR's
  authoring conversation)**: the project owner directed that new or expanded accessibility
  compliance scanning run on a scheduled, non-blocking cadence against `main`, not inside the
  per-PR gate, so that gate does not grow in scope or run time. This is the primary source for
  that ruling; every other reference to it in this repository (CLAUDE.md, the weekly workflow's
  header comment, Decision item 2 below) points back to this paragraph rather than restating it
  as free-standing fact.

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
     WCAG 2.2 A/AA (both `wcag22a` and `wcag22aa`: axe's WCAG tags are additive per level, so
     `wcag22aa` alone would silently skip the 2.2 Level A criteria, the exact pitfall
     `UW-N04` names) plus axe's non-normative "best-practice" rules (missing landmark/heading
     structure, redundant roles, and similar). Kept off Tier 1 both because best-practice findings
     are not WCAG conformance failures and per the Business ruling in Constraints above.
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
- The new Tier 2 scan found real value on its first correct run: 13 test-case failures tracing to
  four distinct structural defects (tracked as `UW-F27`), invisible to the Tier 1 WCAG-only scan
  because they are axe best-practice rules, not WCAG conformance rules.
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

- `eslint-plugin-jsx-a11y`'s peer-dependency range does not yet include `eslint@10`, and the
  `overrides` entry silences the ERESOLVE warning permanently rather than temporarily, which
  removes the signal that would otherwise prompt revisiting it (finding surfaced in this PR's own
  review). Tracked as `UW-F30` below rather than left to memory, since a `Technical debt` bullet
  with no register row is exactly the pattern this project's ADR discipline exists to close.
- Tier 2's first run surfaced findings (`UW-F27`) that remain unfixed as of this ADR; Tier 2 exists
  to keep finding drift like this, not to fix it inline.

## Follow-on work

- **`UW-F27`** (Cluster F, phase 5, unscheduled): fix the four distinct defects behind Tier 2's
  first correct run (13 failing test cases in total, reconciled here: nested `<main>` landmarks on
  admin pages, missing `<h1>` on two pages, `guardian/LoginPage.tsx`'s missing `<main>` landmark,
  and a heading-order skip on the admin review detail page). The nested-`<main>` defect is
  code-confirmed on all six admin pages named in that row, but Tier 2 only ever axe-*scans* four of
  them (`AuthoringQueuePage`, `ModerationDashboardPage`, `ModerationThresholdsPage`,
  `ProviderAllowlistPage`); `AuditPage` (`/admin/audit`) and `UserManagementPage`
  (`/admin/users`) share the identical pattern by code inspection but are never navigated to at
  either tier (the same 11-route gap named above, `UW-F29`), so those two are unconfirmed by any
  running test.
- **`UW-F29`** (Cluster F, phase 5, unscheduled, new): axe-scan the 11 routes named in Context
  that neither tier visits today, starting with `legal/PrivacyPolicyPage.tsx` (`/privacy`) and
  `guardian/PrivacyPage.tsx` (`/guardian/privacy`) since this PR edits both for accessibility
  without ever scanning either, and `/admin/audit`/`/admin/users` since `UW-F27` depends on them.
- **`UW-F30`** (Cluster F, phase 5, unscheduled, new): re-verify (or replace) the
  `eslint-plugin-jsx-a11y` peer-dependency override on the plugin's next release, since the
  override silences the ERESOLVE signal permanently rather than temporarily. See Technical debt.
- **`UW-N04`** (Cluster N, phase 5, unscheduled, updated by this ADR): WCAG 2.2 scanning now runs,
  but on the new weekly Tier 2 job rather than the per-PR gate. Widening the *blocking* gate itself
  to WCAG 2.2, if ever wanted, is still that row's open work.
- **`UW-F28`** (Cluster F, phase 5, decision): a manual screen-reader audit (VoiceOver + NVDA
  minimum, on the core flows: profile picker, reader, guardian intake, admin review), and a
  published accessibility statement naming the WCAG 2.1 AA target and a contact/remediation path.
  Both wait on an owner ruling (scope/budget for the audit, and what the statement commits to)
  before either is schedulable.
- **`UW-I06`/remediation-plan `P14`**: this ADR ships `eslint-plugin-jsx-a11y` despite `P14`'s
  deferral precondition (an eslint-10-compatible peer range) still being unmet upstream. The
  override above is the mitigation, verified against a clean `npm ci`, not a claim that the
  precondition is satisfied. Both rows are updated alongside this ADR to record that the plugin
  shipped anyway and why.
