---
purpose: Consolidated workflow-logic and fidelity review of the full E2E suite, with emphasis on child-facing flows
component: frontend/e2e, frontend/e2e-real, frontend/e2e-staging, frontend/e2e-prod
source: 11 journey-scoped subagent reviews, 2026-07-22, PR #369 branch test/e2e-coverage-backfill
---

# E2E Workflow-Logic and Fidelity Review (2026-07-22)

## Method

59 spec files across four tiers (mocked `e2e/`, real-backend `e2e-real/`,
`e2e-staging/`, `e2e-prod/`) were reviewed by 11 journey-scoped agents. Each
agent held two mandates:

- **Fidelity**: does the test match the code, and would it fail if the real
  experience broke?
- **Desirability**: is the flow the test encodes what a real user, especially
  a child (ages ~5-10, many pre/early readers), would expect and find simple?

Child rubric applied: a child should always know what to tap next; never a
dead end; no adult jargon or error codes; graceful recovery from a wrong tap
or offline; the "find your grown-up" gate the only hard stop.

## Overall assessment

The suite is **faithful and disciplined**: tests generally assert the network
write actually fired (captured request bodies, poll-on-boolean), confirmation
dialogs are exercised, real-tier specs read persisted state back, often through
a second principal. The problems are **not false-green regressions in what is
covered**; they are (a) a small number of **product flows that a child would
not expect**, which the tests currently enshrine as correct, and (b) **coverage
gaps** where a broken real-world experience, especially a child one, would still
pass.

---

## Part 1: CHILD WORKFLOW PRODUCT ISSUES (flow is wrong for the user)

These are places where the tested flow itself is not what a child would expect.
Fixing these is a product change; the test change follows.

### P-1 [HIGH] A child can be shown a blocking, undismissable multi-device conflict dialog
- `ConflictDialog.tsx:70-88`, rendered to the kid surface at `ReaderPage.tsx:566-567`
  (live-save 409) and `ReaderRoute.tsx:220-225` (reconnect replay).
- Mid-story, a 5-10 year old is forced to answer "Which one do you want to keep?
  Keep this device / Use the newest place" before they can read on. "Keep this
  device" can discard the other device's progress.
- Both `reader-conflict.spec.ts:71-72,97-102` and `offline-conflict-real.spec.ts:186-211`
  assert this dialog as correct behavior, locking it in.
- The softer pattern already exists two elements over: the replay-failed banner
  (`ReaderRoute.tsx:227-240`) tells the child gently and defers to a grown-up.
- **Recommend**: auto-resolve conflicts (silently adopt the newest place, never
  lose the child's furthest position); a child should never see a merge prompt.
  Then assert *no* conflict dialog reaches the child.

### P-2 [HIGH] The flag/report path can dead-end a distressed child on a scary error
- `FlagButton.tsx:132-136` renders `role="alert"` "Something went wrong. Try
  again." A child who just reported that a story upset them gets an error alert.
- Untested in both tiers. It is exactly the dead-end the rubric forbids, on the
  most emotionally sensitive path.
- **Recommend**: replace the error with a reassuring, non-blocking message that
  keeps the child in the story or points them to a grown-up; add a test.

### P-3 [MED] The ending screen's "what now" affordances are never asserted (dead-end risk)
- `Reader.tsx:372-397` renders "Read again", "Go back", "Back to my books",
  optional "Continue the series". No spec asserts any of them; `reader.spec.ts:59-60`
  asserts only `ending-screen` + the hidden `ending-id`.
- A regression shipping an ending with no forward action passes every test. The
  rubric's "never a dead end" guarantee is unpinned.

### P-4 [MED] The child PIN gate is untested and the fresh-device login has no child framing
- PIN surface (`ProfilePickerPage.tsx:328-400`: padlock tile, "Type your secret
  PIN", wrong-PIN retry, forgot-PIN "Ask a grown-up" escape) never renders in
  any test because no fixture sets `has_pin`.
- Fresh-device: a child tapping "Kids" lands on a bare adult email/password form;
  no test asserts any "ask your grown-up to set up this device" framing
  (`device-authorization.spec.ts` test 1).
- Both are the child's only hard stops besides AdultGate and both are the highest
  dead-end/confusion risk.

### P-5 [MED] Read-aloud is weak for its actual audience (pre-readers)
- No word/position highlight anywhere in `useReadAloud.ts`; a pre-reader cannot
  follow along visually.
- Flag reason labels are text-only, no icons, no read-aloud (`FlagButton.tsx:36-40`),
  yet a distressed pre-reader may not be able to read "It was confusing."

### P-6 [LOW] Parent-facing copy/flow snags the tests entrench
- "Assign more" shown even for a book assigned to no one yet (`assignments.spec.ts`).
- Two divergent "Request a story" surfaces (`/guardian/intake` concept vs the
  authored form on `/guardian/requests`) with different behavior and different
  success copy; "sent for authoring" leaks jargon with no pointer to where the
  story now appears.
- No UI to delete a child profile (the real test must call DELETE directly,
  `guardian-profile-crud-real.spec.ts`).
- Awaiting-approval interstitial is a soft dead-end: only exit is a `Sign out`
  button, no status re-check/poll/"we'll email you" (`GuardianAwaitingApprovalPage.tsx:56`).
- No new-visitor/sign-up affordance on the landing page; both doors lead to
  existing-user destinations (`LandingPage.tsx:110-123`).

---

## Part 2: CHILD WORKFLOW FIDELITY GAPS (would pass if broken)

### F-1 [HIGH] The security-critical guardian-bearer-shed handoff has zero e2e coverage
- `handDeviceToChild()` (`ConsolePage.tsx:116-121`, the `#CRITICAL` sign-out-
  before-handoff) is never clicked in any tier. Prod/staging reach `/kids` with
  the guardian still signed in; the mocked test that runs the LoginPage sign-out
  path never asserts `auth_token` was cleared (`device-authorization.spec.ts:51-58`).
- A regression re-leaking the family library to a child (PR #247 Critical class)
  passes every one of these tests.

### F-2 [HIGH] The core real reading loop never asserts the child sees any story text
- `kid-reads.spec.ts:49-53` clicks choices to an ending but asserts no passage
  text, ending title, or content change. A backend serving blank/garbled prose
  passes green. The real tier is the one that could actually serve malformed
  prose, and it is the tier with no content assertion.

### F-3 [MED] Read-aloud tests never assert spoken content equals the passage
- `kid-read-aloud.spec.ts:74-80,142`, `kid-read-aloud-real.spec.ts:160-176`.
  `speak()` is stubbed/no-op; a regression speaking the wrong text or nothing
  passes.

### F-4 [MED] The series feature is never proven end-to-end on a real backend
- Mocked (`series-continue.spec.ts:143`) proves carried `var_state` but the
  "opens at entry node" claim is a tautology (`start_node == series_entry_node`).
- Real (`series-continue-real.spec.ts:58-62`) proves the URL but asserts nothing
  about carried state, the defining behavior of `carries_state:true`.
- Neither tier proves both, so the headline series behavior is unproven on a
  real backend.

### F-5 [MED] "naive-kid-misuse-real" contains no child-misuse tests
- The file is a single cross-family authorization check. Real button-mashing
  (double-tap into the real 5-request cap -> 409, rapid choice-mashing, garbage/
  emoji input, offline-mid-request, back-button mid-form, stale-anchor retry) is
  untested against the real backend. Enumerated gaps in the kid-requests review.

### F-6 [LOW] Other child-recovery paths uncovered at e2e level
- Hardware/OS Back button (what a kid mashes on a tablet) has zero coverage; all
  go-back tests drive the in-app control only.
- Offline library shelf and the library "Time to find your grown-up" gate
  (`LibraryPage.tsx:277-297,379-383`) are unit-only.
- Gated-var replay + server persistence of go-back are split across tiers with a
  hole in the middle (`reader-go-back.spec.ts` client-only; `kid-go-back-real.spec.ts`
  ungated story).
- Conflict during offline-reconnect flush (`ReaderRoute.tsx:220`) is component-only.

---

## Part 3: ADULT / SYSTEM FIDELITY + SAFETY GAPS

### S-1 [HIGH] The approve -> assign -> child-sees loop is never tested end-to-end
- Every assign test stops at the POST body (`guardian-books.spec.ts:142,200`,
  `assignments.spec.ts:117`). The one real test where a child reads a book uses a
  fixture-pre-assigned book (`reading-history-real.spec.ts`), not a guardian-driven
  assignment. The single most non-obvious required step in the product (a book is
  approved but invisible until separately assigned) is unverified from guardian
  action through to the child's library.

### S-2 [HIGH] Catalog-visibility publish is entirely untested end-to-end
- The approve dialog's `catalog` option publishes to every family with a PII
  warning (`ReviewDetailPage.tsx:663-689`). No test selects it, asserts the
  warning, or even inspects the approve POST body to confirm `visibility` reaches
  the wire (`guardian-review.spec.ts:72-95`). Highest-consequence child-privacy
  decision on the surface.

### S-3 [HIGH] Cross-family PII compensating controls unverified
- The `PROFILE_VIEWED` cross-tenant read audit (`admin_profiles.py:119-134`) and
  the `pin_hash`/`authn_subject` non-serialization boundary are never asserted by
  the tier that receives real cross-family JSON (`admin-management-real.spec.ts`).
- The server-side admin 403 gate is never exercised; both guardian-redirect tests
  assert only the client SPA redirect. Self-lockout guard and privilege escalation
  (granting `is_admin:true`) have zero e2e coverage.

### S-4 [MED] The human-approval safety invariant is proven only positively
- `approval-flow.spec.ts:78-88` shows an approved story reaching the child library,
  but nothing asserts an `in_review`/`needs_revision` story is ABSENT from it.
  "No child content without human approval" is never demonstrated by pre-approval
  invisibility.
- Re-screen-after-edit is unobservable (mock keeps original findings,
  `review-edit.spec.ts:96-105`); the 422 unsafe-edit-rejected branch is
  component-only.

### S-5 [MED] The crown-jewel full-pipeline stubs the content it is meant to prove safe
- `full-pipeline-real.spec.ts:22-25,63` runs the real worker/queue/DB/approve/
  reader but the mock generation provider (canned "The Forest Path"). The gate can
  only ever be observed passing; no hard-block/send-back negative path exists
  anywhere. It also routes around the real family request/intake/gating surface
  (uses the UI-less `/api/v1/concepts`), so it is a realistic generate-and-publish
  journey, not the realistic family journey.

### S-6 [MED] Real-tier request paths weaker than their mocks
- `authored-request.spec.ts:35,53` asserts only the success notice; a backend that
  201s but does nothing downstream passes. The concept-intake pipeline has no
  real-backend test at all.

### S-7 [LOW] Auth negatives asserted only positively
- Cross-tab password recovery proves tab B shows the new-password form but not that
  it avoided an old-password signed-in console (`guardian-password-reset.spec.ts:161-191`).
- Post-login deep-link `state.from` return-path untested (`guardian-console.spec.ts:32-37`).
- Sign-out "re-locks" asserts only the URL, never re-navigates to prove re-gating
  (`guardian-auth.spec.ts:92-103`).

---

## Genuine strengths (models to copy)

- `offline-online-parity-real.spec.ts`: offline is silent to the child; reconnect
  confirms with a friendly "All caught up! Your reading is saved."; cross-engine
  Python replay. The right pattern.
- `kid-flag-real.spec.ts` and `kid-go-back-real.spec.ts`: assert persisted server
  state through a second principal, not just a toast.
- `contract-smoke-real.spec.ts`: field-by-field real-shape pinning against named
  consumers, the drift class behind P0-1.
- `guardian-consent.spec.ts`: the only test that proves a gate is not client-side
  bypassable (re-navigates after consent).
- `library.spec.ts`: locks in "decorations degrade to absence, never an error"
  and the ADR-016 no-messaging boundary.
- `a11y.spec.ts` / `visual.spec.ts`: structurally CI-gated, animation-settled,
  meaningful floors.
