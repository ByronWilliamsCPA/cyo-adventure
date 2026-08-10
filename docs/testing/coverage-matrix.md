---
title: "Frontend Test Coverage Matrix"
schema_type: common
status: published
owner: core-maintainer
purpose: "Maps each user journey to the tests that cover it, by layer and environment."
tags:
  - testing
  - coverage
---

Maps each user journey to the tests that cover it, by layer and environment.
Use this to answer "what covers X" and to spot gaps before they reach staging
or production. See [`docs/testing/README.md`](README.md) for the environment
tiers this matrix references (local, dev, staging, production) and how they
relate to the Supabase project constraints.

## How to read this

- **Layer**: Unit/Component (Vitest + Testing Library), E2E-mocked (Playwright
  against route-intercepted API, `frontend/e2e/`), E2E-real (Playwright
  against a real local backend, `frontend/e2e-real/`), E2E-staging (Playwright
  against the shared staging Supabase project's seeded fixtures,
  `frontend/e2e-staging/`, scheduled + manual), E2E-prod (Playwright against
  live production, `frontend/e2e-prod/`, manual plus one scheduled workflow
  that deliberately overrides the tier's CI guard).
- "NONE FOUND" means no test at that layer touches this journey. It does not
  necessarily mean the journey is unimplemented, only untested at that layer.

## Cross-cutting checks (not tied to one journey)

- **Accessibility**: `frontend/e2e/a11y.spec.ts` — axe-core, scoped to WCAG
  2.1 A/AA, across every top-level page (landing, kid picker, kid library
  populated/empty, reader, guardian login/console/intake/requests/
  books/profiles, admin console/requests/moderation-thresholds/
  moderation-dashboard) and every modal/dialog surface (ConflictDialog,
  AssignChildrenDialog, ProfileFormDialog). `/admin/review/:id` was excluded
  through 2026-07-22, same reasoning as `e2e-prod/guardian-admin-smoke.spec.ts`:
  it needs a real storybook id and a dynamic heading. The 2026-07-27 pass lifted
  that exclusion (an axe scan needs no fixed heading, only a stable seeded
  fixture) and now scans the review detail in both its flagged-passage and
  approve-failure-alert states. The same pass added populated-fixture scans of
  the admin thresholds, dashboard, provider-allowlist, and review-queue
  surfaces, whose colored severity pills, content-flag/valence badges, and
  inline error alerts never rendered under the original empty-fixture scans and
  so were never contrast- or name-role-checked. Across two passes (2026-07-16) found
  six real contrast failures, all traced to two design-system tokens
  (`--color-amber-deep`, `--color-ink-muted`) used against a darker
  background than their documented contrast math assumed; fixed the same
  day (see `--color-amber-deep-text` in `design-system/src/tokens.css`, the
  `.cyo-btn--primary`/`.cyo-btn--ghost` fixes in `Button.css`, and the
  `--color-ink-secondary` swaps in `guardian.css`/`kid.css`/`library.css`/
  `landing.css`). The dialog pass found no new violations. Remaining gap:
  outside the populated and error-alert scans added above, each remaining
  page/dialog is still checked in one fixed mock state, not every
  loading/error variant.
- **Keyboard operability of dialogs (2026-07-27)**:
  `frontend/e2e/keyboard-nav.spec.ts` — the focus behavior axe cannot see,
  asserted against the real built app. Three representative `cyo-dialog` modals
  (the admin review Approve dialog, the guardian Profile form dialog, and the
  guardian Assign-children dialog) must each satisfy the same contract: opening
  moves real DOM focus into the dialog, Tab off the last focusable wraps to the
  first and Shift+Tab off the first wraps to the last (focus never escapes to
  the page behind), and Escape closes the dialog and restores focus to the
  trigger that opened it. Two further tests pin the textarea-primary dialogs
  (admin review Send Back and Edit passage): pressing Tab from the opened dialog
  must reach the reason/passage textarea. Those two are a regression guard for a
  real WCAG 2.1.1 defect found and fixed in this pass: the shared Dialog
  focus-trap selector omitted `textarea`, so a keyboard-only admin could neither
  type a send-back reason nor edit a passage, and the trap leaked once a mouse
  user clicked into the field. Remaining gap: the three dialogs above stand in
  for the shared component, so a dialog that hand-rolls its own focus handling
  instead of using `cyo-dialog` would not be caught here.
- **Visual regression**: `frontend/e2e/visual.spec.ts` — screenshot
  baselines for every top-level page and every modal/dialog surface:
  landing, kid picker, reader (+ conflict dialog), library, guardian
  console/intake/requests/books (+ assign dialog)/profiles (+ profile-form
  dialog), and admin console/requests/moderation-thresholds/moderation-
  dashboard (`visual.spec.ts-snapshots/`). Same remaining-gap caveat as
  accessibility above: one state per surface, not every variant.
- **Cross-device/cross-browser responsiveness (2026-07-24)**:
  `frontend/e2e/responsive.spec.ts` and `frontend/e2e/cross-device.spec.ts`
  (shared checks factored into `frontend/e2e/support/responsiveChecks.ts`) —
  structural (not pixel-diff) checks across landing, kid picker, library,
  reader, guardian console, admin console, and the admin user-management
  table: zero page-level horizontal overflow, plus a regression guard that a
  single-item library shelf fills its row instead of leaving a dead empty
  grid track. `responsive.spec.ts` sweeps three viewport widths (desktop/
  tablet/mobile) on the `chromium` project; `cross-device.spec.ts` runs the
  same checks once per real device/browser project (`cross-device-mobile`:
  Pixel 7, `cross-device-tablet`: iPad (gen 7)/webkit, `cross-browser-
  mobile-safari`: iPhone 14/webkit, `cross-browser-firefox`: Desktop
  Firefox — `npm run test:e2e:cross-device`, wired into its own
  `cross-device-e2e.yml` workflow rather than `ci.yml`'s `frontend` job:
  `playwright install --with-deps firefox webkit` apt-installs a much larger
  dependency set than chromium alone, which pushed `frontend`'s 15-minute
  timeout the first time this ran inline. `cross-device-e2e.yml` is
  informational (not a merge gate), same posture as `e2e-real-pr-smoke.yml`,
  until its per-PR reliability is established. Found and fixed three real
  bugs neither the existing Desktop-Chrome-only suite nor visual.spec.ts's
  single-viewport baselines caught: `library.css`'s shelf grid used
  `auto-fill` (reserves empty tracks) instead of `auto-fit` (collapses
  them); `guardian.css`'s admin/guardian table `overflow-x: auto` escape
  valve was scoped to a `max-width: 640px` breakpoint, leaving
  tablet-portrait widths (641-900px) with no scroll fallback for a table
  wider than the viewport; and (found after rebasing onto the newly-merged
  ThemeToggle feature) `.guardian-shell__header` had no wrap behavior, so
  its three action buttons (theme toggle, notification bell, sign-out)
  overflowed the header at phone widths. Remaining gap: only the `chromium`
  project's Desktop Chrome run is verified in every environment;
  firefox/webkit device projects need `playwright install firefox webkit`
  and are exercised in CI, not in every local dev sandbox.
- **API contract pinning (G2, Phase 7.2)**: `frontend/e2e-real/contract-smoke-real.spec.ts`:
  a real-backend contract smoke that pins the real API response shape for
  the four highest-drift endpoints the mocked `page.route` tier only assumes:
  `GET /api/v1/library` (the `BookCard`/`LibraryPage` fields), `PUT
  /api/v1/reading-state/{profile}/{story}` (the player/offline-sync
  `ReadingState` fields), `POST` + `GET /api/v1/story-requests` (the
  `StoryRequestQueue` fields), and `GET /api/v1/review-queue` +
  `GET /api/v1/storybooks/{id}/review` (the admin review-console fields).
  Spans multiple journeys, so it is registered here rather than under a
  single one; guards against the failure class behind the prior P0-1
  offline-resync 422, where a real backend field changed while every mocked
  fixture kept passing.
- **Full generation pipeline, end to end (G1, Phase 7.1)**:
  `frontend/e2e-real/full-pipeline-real.spec.ts`: the one spec that drives a
  story through the *real* RQ generation worker rather than seeded data:
  a guardian `POST /api/v1/concepts` + `/generate`, a real `generation_job`
  polled until the worker (mock provider, but the full staged validator +
  moderation gate) lands it at `in_review`, then the real admin approve/publish
  UI, then the seeded child reads the produced story to an ending. Runs in its
  own `real-backend-pipeline` Playwright project (`npm run test:e2e:real:pipeline`)
  because it is the only real-backend spec that additionally requires a running
  `python -m cyo_adventure.generation.worker_main`; the deterministic Phase 4.2
  reset also purges each run's worker-generated storybook so consecutive runs
  stay clean. Spans every backend stage between request and read, so it is
  registered here rather than under a single journey. Intended for the nightly
  real-stack job (a worker must be started before it runs, or its poll deadline
  fails with an explicit worker-not-running message).
- **Full generation pipeline, the BLOCKING direction (S-5)**:
  `frontend/e2e-real/full-pipeline-negative-real.spec.ts`: the negative twin of
  the spec above. Where `full-pipeline-real.spec.ts` proves the gate *passing*
  on the gate-clean canned story, this one drives the same real
  request -> generate -> gate path to a HARD BLOCK: a guardian `POST
  /api/v1/concepts` + `/generate`, a real `generation_job` polled through the
  real RQ worker to a terminal `needs_review`/`failed` status, then two
  containment assertions, that no Storybook row is persisted for the blocked
  run, and that the would-be storybook id never appears in the admin
  `GET /api/v1/review-queue` (so a blocked story can never be approved,
  published, or assigned to a child). Requires the backend to run with
  `ENVIRONMENT=local`, `CYO_ADVENTURE_GENERATION_PROVIDER=mock`, and
  `CYO_ADVENTURE_MOCK_STORY_FIXTURE=invalid`; that last var (added for S-5,
  see `core/config.py::Settings.mock_story_fixture`) serves the structurally
  broken `_INVALID_STORY` fixture the validator's topology check rejects at
  ERROR severity on every repair attempt. It defaults to `safe`, so a default
  backend produces a passing run and fails this spec's block assertion with an
  explicit "is MOCK_STORY_FIXTURE=invalid set?" message rather than a silent
  pass. Spans every backend stage between request and gate, so it is registered
  here rather than under a single journey. **Authored, not yet executed**: the
  remediation session that wrote it had no local backend, so only `tsc -b`,
  ESLint, and `playwright --list` verified it; run it against a real stack (with
  the env vars above and a running worker) before trusting it as proven.
- **Per-PR real-stack smoke (G4, Phase 7.4)**: `frontend/e2e-real/kid-reads.spec.ts`,
  run on the PR path via the `real-backend-pr-smoke` Playwright project
  (`npm run test:e2e:real:pr-smoke`, workflow `.github/workflows/e2e-real-pr-smoke.yml`).
  The full `real-backend` tier is nightly-only for cost; this promotes exactly
  one fast, seeded, happy-path read (no worker, no live generation) to every PR
  so contributors get a real full-stack signal per change. Deliberately
  **informational, not a merge gate**: it triggers on `pull_request` only (no
  `merge_group`) and is not a branch-protection required check, so a red run is
  a signal to investigate rather than a block; it can be promoted to required
  once its per-PR flakiness rate is known. The same spec also runs under
  `real-backend` in the nightly (one spec, two projects).
- **Mobile-web tap targets (Task A7, mobile-safari)**:
  `frontend/e2e/admin-touch-targets.spec.ts` — asserts every action button in
  the six admin CRUD surfaces migrated to the `@ds` `Button` (FamiliesTab,
  KidsTab, ConnectionsTab, UsersTab, ProviderAllowlistPage, AuditPage) plus the
  two moderation pages' trigger/submit buttons clears the 44x44 minimum (WCAG
  2.5.5) at a phone viewport, scoped per `main section` content container so the
  regression stays pinned to the migrated buttons rather than chrome. Asserted
  height-only until 2026-07-27, when the width assertion was added alongside the
  kid sweep below; WCAG 2.5.5 is both axes.
- **Kid reader tap targets (2026-07-27, both axes)**:
  `frontend/e2e/kid-touch-targets.spec.ts` — the same 44x44 WCAG 2.5.5 floor for
  the surface the app's primary users actually touch: every visible choice
  button the reader renders (`.reader-choices button:visible`) is measured on
  both axes at a 390x844 phone viewport, with a count assertion so a selector or
  route typo cannot silently pass an empty check. The bullet above is
  admin-scoped, which left the kid reader's choice buttons, the highest-traffic
  control in the product, with no tap-target guard at all until this landed.
- **Mobile-web narrow-width overflow sweep (Task A12, mobile-safari)**:
  `frontend/e2e/mobile-viewport.spec.ts` — runs under the `mobile-safari`
  project (`npm run test:e2e:mobile`); asserts zero horizontal overflow at real
  phone widths across landing, kid picker/library, and guardian surfaces. Guards
  fluid-layout overflow only; Playwright device profiles do not emulate
  `env(safe-area-inset-*)`, so notch/home-indicator overlap (Task A8) needs a
  real device or the Capacitor build.
- **Guardian-facing redaction contract, live production**:
  `frontend/e2e-prod/guardian-books-and-isolation.spec.ts` installs a
  whole-suite response collector before sign-in, capturing every `/api/v1`
  JSON response body fetched anywhere in the suite, then asserts none of them
  ever carries `flagged_passages` or a bare `prose` key at any depth: the
  exact admin-only fields `review_surface.py::build_content_summary` must
  redact out of a guardian-facing `ContentSummaryView`. A positive control
  fails the run if the collector captured zero bodies, so the assertion
  cannot pass vacuously. Spans every request the suite makes rather than one
  journey, so it is registered here.
- **Platform health and ingress routing (register item UW-L04)**:
  `frontend/e2e-prod/health-probe.spec.ts`, unauthenticated and
  credential-free (Playwright's `request` fixture, no browser page), against
  live production: the canonical `GET /api/v1/health/ready` returns real
  FastAPI JSON (status 200, `content-type: application/json`, `status` and
  `checks` keys); the previously-shadowed `GET /health/ready` returns exactly
  404, asserted as 404 rather than as "not 200" so a whole-site outage cannot
  satisfy it, because nginx's stub moved to `location = /nginx-health` and
  `/health` now answers an explicit `return 404` (deleting the block instead
  would have let the path fall through to the SPA `try_files` fallback and
  answer `200 text/html`, the same false pass in a new disguise); and `GET
  /nginx-health` (a plain-text, nginx-only control) still answers 200, so a
  failure of the canonical check can be told apart from the whole ingress
  being down. Not a user journey: this guards the ingress and health-router
  wiring itself, the regression behind the month-long UW-L04 false pass where
  nginx silently shadowed FastAPI's real readiness logic.

---

## Landing page / marketing

- E2E-mocked: `frontend/e2e/landing.spec.ts`
- E2E-prod: `frontend/e2e-prod/landing-login.spec.ts`
- Component: `frontend/src/landing/LandingPage.test.tsx`
- Integration: `frontend/src/test/App.test.tsx`

## Guardian: login/auth

- E2E-mocked: `frontend/e2e/guardian-auth.spec.ts`, `frontend/e2e/guardian-console.spec.ts` (redirect matrix), `frontend/e2e/intake.spec.ts` (unauth redirect), `frontend/e2e/naive-user/naive-misuse-shared.spec.ts` (expired-session redirect)
- E2E-real: `frontend/e2e-real/approval-flow.spec.ts` (access-control checks)
- E2E-staging: `frontend/e2e-staging/guardian-admin-smoke.spec.ts` (real Supabase sign-in as both seeded guardian and admin accounts)
- E2E-prod: `frontend/e2e-prod/landing-login.spec.ts`, `frontend/e2e-prod/guardian-admin-smoke.spec.ts`,
  `frontend/e2e-prod/guardian-profiles.spec.ts` (unauthenticated visit redirects to sign-in; login page shows
  Google and hides Apple; sign-out returns to sign-in both client-side and after a fresh reload)
- Component: `frontend/src/guardian/LoginPage.test.tsx`, `frontend/src/guardian/SetNewPasswordForm.test.tsx`, `frontend/src/auth/AuthContext.test.tsx`, `frontend/src/auth/AdultGate.test.tsx`, `frontend/src/auth/ProtectedRoute.test.tsx`, `frontend/src/auth/GuardianBackendUnavailablePage.test.tsx`, `frontend/src/auth/guardianToken.test.ts`, `frontend/src/auth/supabaseClient.test.ts`, `frontend/src/guardian/GuardianShell.test.tsx`, `frontend/src/guardian/ConsolePage.test.tsx`
- Integration: `frontend/src/test/App.test.tsx`
- **Backend-unreachable branch (issue #452):** when the Supabase session is
  valid but principal resolution fails transiently (no response, or a 5xx from
  our API or an intermediary), the session is KEPT and the guardian lands on
  the `/guardian/unavailable` retry interstitial instead of being looped
  through login. Covered at the component tier from both ends:
  `frontend/src/auth/AuthContext.test.tsx` pins the classification matrix
  (500/502/503/504 and a network error are transient and retain the token;
  400/401/403/404/422 and a non-axios throw stay terminal and clear it), and
  `frontend/src/auth/GuardianBackendUnavailablePage.test.tsx` covers the
  interstitial itself, manual retry, the 15-attempt auto-retry cap, and the
  redirect out on every recovered status. The three sibling status consumers
  (`LoginPage`, `GuardianConsentPage`, `GuardianAwaitingApprovalPage`) each
  carry a redirect test in their own file.
- **Gap**: no E2E tier exercises the backend-unreachable branch. Reproducing it
  needs the API to fail while Supabase keeps succeeding, which the mocked tier
  can express (fulfil `/api/v1/**` with a 503 after sign-in) but no spec does
  yet. Component coverage is the whole of it today.
- **Google OAuth sign-in (decision 2.6, manual-only flow + automated option
  presence):** the full Google OAuth *round trip* is not automated at any tier
  and is not automatable without a live Google session (faking the provider
  redirect asserts nothing about the real integration), so the end-to-end flow
  is a **manual check**: on staging (Google is live there), click "Continue
  with Google" on `/guardian/login` and confirm the redirect completes to a
  signed-in console. What IS automated is the part worth automating, that the
  option renders where expected: `frontend/src/guardian/LoginPage.test.tsx`
  (asserts the "Continue with Google" button is present) and
  `frontend/src/auth/AdultGate.test.tsx` (asserts the Google option renders for
  a Google-linked adult and that clicking it starts the `signInWithOAuth`
  redirect). The Apple button is intentionally gated off behind
  `VITE_ENABLE_APPLE_OAUTH` until that provider is live (`LoginPage.tsx`).

## Guardian: password recovery (reset link + set new password)

The Supabase-backed forgot-password journey: request a reset email, then set a
new password from the recovery link, including the cross-tab handoff (a
recovery link opened in one tab must surface the set-new-password form in
another open tab, via the `cyo-guardian-recovery` `BroadcastChannel`). These
are GoTrue calls (`auth/v1/...`), not app-API calls, so the E2E mocks the
Supabase endpoints rather than `/api/v1`.

- E2E-mocked: `frontend/e2e/guardian-password-reset.spec.ts` (request-a-reset asserts the `POST auth/v1/recover` fired and the neutral confirmation renders; set-new-password drives a real implicit-grant recovery hash to a signed-in redirect and asserts the exact `PUT auth/v1/user` body; the cross-tab test opens two pages in one `BrowserContext` and proves the recovery `BroadcastChannel` surfaces the set-new form in the second tab)
- Component: `frontend/src/guardian/ResetPasswordRequestForm.test.tsx`, `frontend/src/guardian/SetNewPasswordForm.test.tsx`
- **Gap**: no `e2e-real`/`e2e-staging`/`e2e-prod` coverage; a real reset requires a live inbox, so staging durability (recording seeded passwords in a secret manager) is tracked separately in the audit handoff, not here.

## Guardian: consent gate (privacy notice / COPPA e-signature)

- E2E-mocked: `frontend/e2e/guardian-consent.spec.ts` (needs-consent gate ->
  legal-name + checkbox e-signature submit -> signed-in console; asserts the
  exact `POST /v1/onboarding` consent payload and name trimming; plus the
  awaiting-approval interstitial branch)
- Component: `frontend/src/auth/GuardianConsentPage.test.tsx`,
  `frontend/src/auth/GuardianAwaitingApprovalPage.test.tsx`
- **Note**: the gate is driven by the `POST /v1/onboarding` response fields
  (`consent_recorded`, `status`), NOT `/v1/me`; see the spec header. This was
  every guardian's first screen yet only manually prod-verified before the
  2026-07-22 audit added the E2E above.

## Guardian: submit story request (intake)

- E2E-mocked: `frontend/e2e/intake.spec.ts`, `frontend/e2e/story-requests-authored.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts` (double-submit), `frontend/e2e/naive-user/naive-misuse-shared.spec.ts`
- E2E-real: `frontend/e2e-real/authored-request.spec.ts`
- E2E-prod: `frontend/e2e-prod/guardian-admin-smoke.spec.ts` (render only)
- Component: `frontend/src/guardian/IntakePage.test.tsx`, `frontend/src/guardian/RequestStoryForm.test.tsx`, `frontend/src/guardian/intakeApi.test.ts`, `frontend/src/guardian/authoredRequestApi.test.ts`

## Guardian: screening/anchoring flow

- E2E-mocked: `frontend/e2e/intake.spec.ts` (poll to "Waiting for review"), `frontend/e2e/story-requests-authored.spec.ts` (blocked-content response), `frontend/e2e/story-requests-kid.spec.ts` (anchor via `anchor_storybook_id`)
- Component: `frontend/src/guardian/StoryRequestQueue.test.tsx` (dedicated coverage of the shared queue component's anchored-row branching: disabled/aria-linked age-band select, hidden series-title input, continuation note, teen-only narrative style field, series_title trimming in the approve payload, moderation-flag rendering, blocked-request text fallback); `frontend/src/guardian/RequestsPage.test.tsx` (one anchored-row continuation-note case at the page level); `screened`/`flagged_count` fields also ride along in `ReviewDetailPage.test.tsx`, `AdminConsolePage.test.tsx`, `AssignChildrenDialog.test.tsx`, `FlagBadge.test.tsx`, `BooksPage.test.tsx`
- **Closed**: there is no separate frontend `screening.ts`/`anchoring.ts` module (that logic lives in the backend's `story_requests/`); the actual gap was that `StoryRequestQueue.tsx`, the shared component both adult surfaces embed, had no test file of its own. `StoryRequestQueue.test.tsx` closes that.

## Guardian: review family requests queue

- E2E-mocked: `frontend/e2e/story-requests.spec.ts`, `frontend/e2e/naive-user/naive-guardian-misuse.spec.ts`, `frontend/e2e/naive-user/naive-misuse-shared.spec.ts`
- E2E-prod: `frontend/e2e-prod/guardian-admin-smoke.spec.ts` (render only),
  `frontend/e2e-prod/guardian-books-and-isolation.spec.ts` (the queue's
  empty-state heading and copy as a cross-family isolation signal, read only)
- Component: `frontend/src/guardian/RequestsPage.test.tsx`, `frontend/src/guardian/storyRequestQueueApi.test.ts`, `frontend/src/guardian/AssignChildrenDialog.test.tsx` (tags)

## Guardian: manage books/library

- E2E-mocked: `frontend/e2e/guardian-books.spec.ts`, `frontend/e2e/naive-user/naive-guardian-misuse.spec.ts` (empty state)
- E2E-prod: `frontend/e2e-prod/guardian-admin-smoke.spec.ts` (render only),
  `frontend/e2e-prod/guardian-books-and-isolation.spec.ts` (populated books
  list with a content-review flag badge on each row, read only)
- Component: `frontend/src/guardian/BooksPage.test.tsx`, `frontend/src/guardian/assignApi.test.ts` (listBooks), `frontend/src/guardian/BookDetailsDialog.test.tsx` (book-detail popover: age band, themes, content flags, caller-supplied moderation badge, and the omit-when-absent branches)

## Guardian: manage child profiles

- E2E-mocked: `frontend/e2e/guardian-profiles.spec.ts`, `frontend/e2e/naive-user/naive-guardian-misuse.spec.ts` (empty state), `frontend/e2e/story-requests-authored.spec.ts` (child selector), `frontend/e2e/guardian-preview-as-child.spec.ts` (the guardian's read-only preview of a child's library: rating and request controls suppressed via `LibraryPage`'s `readOnly` prop, the generic banner when the profile lookup fails, and an unauthenticated visit redirected to guardian login)
- E2E-real: `frontend/e2e-real/guardian-profile-crud-real.spec.ts` (a guardian creates and edits a child profile through the real `POST`/`PATCH /v1/profiles` endpoints, both states persisting across reload; `ProfilesPage.tsx` has no delete control by design, so the erasure path, `DELETE /v1/profiles/{id}`, GDPR Article 17 / COPPA 312.10, is exercised via a direct authenticated fetch and confirmed gone from the console on reload)
- E2E-prod: `frontend/e2e-prod/guardian-admin-smoke.spec.ts` (render only),
  `frontend/e2e-prod/guardian-profiles.spec.ts` (profile count against the
  isolated test family; create-profile dialog opened to confirm the avatar
  picker renders and cancelled without submitting),
  `frontend/e2e-prod/guardian-books-and-isolation.spec.ts` (profile count as
  a cross-family isolation signal, read only)
- Component: `frontend/src/guardian/ProfilesPage.test.tsx`, `frontend/src/guardian/ProfileFormDialog.test.tsx`, `frontend/src/profiles/AvatarCircle.test.tsx`, `frontend/src/profiles/profilesApi.test.ts`, `frontend/src/guardian/PreviewAsChildPage.test.tsx` (guardian preview-as-child: read-only `LibraryPage` render for a family profile, `data-age-band`/`data-reduce-motion` propagation, and the generic-banner fallback when the profile lookup fails)

## Guardian: assign children to books

- E2E-mocked: `frontend/e2e/assignments.spec.ts`, `frontend/e2e/guardian-books.spec.ts`, `frontend/e2e/naive-user/naive-misuse-shared.spec.ts` (double-click guard)
- E2E-real: `frontend/e2e-real/assign-visibility-real.spec.ts` (the full approve -> assign -> child-sees loop end to end: a guardian assigns an approved book via `/guardian/books` and the assigned child's real library gains it, while a never-assigned child's library never shows it; causal negative (same child empty before assignment) and concurrent negative (a second unassigned child) prove the assignment step is what makes the book visible, not approval alone)
- E2E-prod: `frontend/e2e-prod/guardian-books-and-isolation.spec.ts` (opens the assign dialog and inspects its
  redacted content-review tags, then cancels via Cancel only; nothing is assigned)
- Component: `frontend/src/guardian/AssignChildrenDialog.test.tsx`, `frontend/src/guardian/assignApi.test.ts`

## Guardian: approve and publish a story

- E2E-mocked: `frontend/e2e/guardian-review.spec.ts`, `frontend/e2e/naive-user/naive-admin-misuse.spec.ts` (concurrent-approve, documents server gap #129), `frontend/e2e/naive-user/naive-misuse-shared.spec.ts` (double-click/back-button/hand-typed-URL guards, #130)
- E2E-real: `frontend/e2e-real/approval-flow.spec.ts`
- Component: `frontend/src/admin/ReviewDetailPage.test.tsx`, `frontend/src/guardian/reviewApi.test.ts`, `frontend/src/guardian/storyRequestQueueApi.test.ts` (approve/decline for pending requests), `frontend/src/guardian/RequestsPage.test.tsx` (approve/decline)

## Guardian: notifications (G10)

- E2E-mocked: `frontend/e2e/guardian-notifications.spec.ts` (a guardian sees the unread-count badge from the notifications poll, opens the bell panel, sees a safety alert rendered with a visually distinct `--alert` class from an informational item, and the badge clears once the panel is opened)
- E2E-real: `frontend/e2e-real/notifications-real.spec.ts` (a real admin approval fires a real `RELEASED` pipeline event, which `notifications/registry.py` composes into a "story_ready" item; the guardian's real `GET /v1/notifications` feed carries it, the bell reflects it, and it survives a reload. The backend keeps no server-side read/unread state for this slice, so "marking read" is the client-side `markSeen()`/localStorage model asserted directly, confirmed here to hold against the real backend's `since`-filtered poll rather than a mocked response)
- Component: `frontend/src/guardian/NotificationBell.test.tsx`, `frontend/src/guardian/notificationsApi.test.ts`, `frontend/src/guardian/notificationSeenStore.test.ts`, `frontend/src/guardian/notificationsStream.test.ts` (the realtime SSE transport layer only, not the generated `createSseClient` it wraps: no guardian token means `onError` and no connection opened at all, a stored token becomes an `Authorization: Bearer` header on a `/notifications/stream` URL that carries `since` only when a prior `lastSeenAt` is known, retries are capped at 5 so a permanently-broken stream cannot loop forever, a `notification` frame is delivered parsed while a keep-alive frame with no event name and no data is ignored, connection errors are forwarded to `onError`, and `close()` aborts the underlying signal)
- **Gap**: no `e2e-staging` or `e2e-prod` coverage yet.

## Guardian: reading history / engagement (G9)

- E2E-mocked: `frontend/e2e/guardian-reading.spec.ts` (a guardian opens Reading from the nav, sees a per-child summary card, expands it to fetch that profile's per-book reading history, and a childless family sees an empty state linking to Books)
- E2E-real: `frontend/e2e-real/reading-history-real.spec.ts` (the seeded child reads "The Clockwork Garden" to its `e_clock` ending against the real backend, producing a real `Completion` row; the guardian then opens Reading and the real `GET /v1/families/me/reading-summary` and `GET /v1/reading-history/{profile_id}` responses show the read reflected in the expanded card)
- Component: `frontend/src/guardian/ReadingPage.test.tsx`, `frontend/src/guardian/readingApi.test.ts`
- **Gap**: no `e2e-staging` or `e2e-prod` coverage yet.

## Guardian: family connections consent (ADR-016 ring 2, G17)

The guardian's own side of a cross-family recommendation link (the "cousins"
case, set up by an app admin). Privacy-load-bearing: nothing crosses a family
boundary until BOTH families' guardians consent (dual-consent), and either
guardian can revoke unilaterally and immediately. Both mutations are gated
behind a confirmation dialog.

- E2E-mocked: `frontend/e2e/guardian-connections.spec.ts` (allow gates the `POST /v1/family-connections/{id}/consent` behind the confirm dialog then flips the row to the waiting-on-counterpart state; revoke gates the `DELETE .../consent` behind its own dialog then reverts the row; both assert the mutation does NOT fire until the dialog is confirmed, at the network layer)
- E2E-real: `frontend/e2e-real/connections-enforcement-real.spec.ts` (dual-consent enforcement proved through the K17 recommendation feed rather than the guardian UI: two real families are provisioned, and a cross-family recommendation becomes visible only once BOTH guardians have consented, disappearing again on unilateral revoke; includes one real rendered kid library assertion. Runs on the nightly `real-backend-pipeline` project, not on PRs)
- Component: `frontend/src/guardian/ConnectionsPage.test.tsx`, `frontend/src/guardian/connectionsApi.test.ts`
- **Note**: the admin-side of connections (creating the link) is covered separately under WS-J (`frontend/src/admin/ConnectionsTab.test.tsx`).
- **Gap**: no `e2e-staging` or `e2e-prod` coverage yet.

## Guardian: data-privacy page (G11 trust surface)

The plain-language account of how family data is handled, at
`/guardian/privacy`, reached from the guardian shell footer. Static content
with no data layer, so the tests are not about behaviour: they pin the
sentences that would become false if someone edited the page without checking
the code behind it. That is the real risk for a trust surface, because a
guardian acts on what it says.

- Component: `frontend/src/guardian/PrivacyPage.test.tsx` (pins the load-bearing claims: the "not the legal privacy notice" disclaimer, "stops with an error rather than carrying on" for the PII guard's hard fail, the outside-classifier disclosure, AI authorship plus the human approval gate, no-training, and "stays with your family by default" rather than an absolute never-shared claim), `frontend/src/guardian/GuardianShell.test.tsx` (footer link present for guardian and admin, and deliberately NOT inside the main nav)
- E2E-mocked: `frontend/e2e/guardian-privacy.spec.ts` (the page reached in the routed app: its load-bearing claims render, the guardian-shell nav links resolve to their real hrefs with Profiles click-tested through, and an unauthenticated visit redirects to guardian login)
- **Gap**: no `e2e-real`, `e2e-staging`, or `e2e-prod` coverage. The page is static and its claims are pinned at the component tier, so the higher tiers would only re-assert that a link navigates.

## Public: privacy policy and support (signed-out)

The two pages at `/privacy` and `/support`, reachable with no account and no
session. These are the URLs registered with Epic's Kids Web Services (ADR-018
D1), so the reader is often a parent partway through a third-party verification
flow rather than someone already inside the app.

Two distinct risks are covered here, and they need different tiers. The first is
placement: a gate on either route would bounce a mid-verification parent to a
login page from a consent flow, which reads as a phishing redirect. That is a
property of the route config, not of the components, so it is asserted against
the config. The second is claim accuracy: a privacy policy that overclaims is
acted on by parents and is a regulatory exposure in its own right, so the tests
pin both the load-bearing claims and the claims deliberately withheld.

- Component: `frontend/src/legal/PrivacyPolicyPage.test.tsx` (renders with no auth provider mounted; pins the contact route against the shared constant, the never-collected-from-a-child list including location, the Epic recipient row naming both the parent email and the child's country, the hard-fail wording for the PII guard rather than a removal claim, and the four claims held back pending counsel or unfinished work: per-purpose GDPR legal basis, processor-only use, a named transfer mechanism, and re-consent on material change), `frontend/src/legal/SupportPage.test.tsx` (same signed-out render, contact route, and the FAQ entries that restate policy claims)
- Config: `frontend/src/router.test.tsx` (structural assertions over the exported route config without rendering: both public paths resolve outside every gate, with a positive control on a known-gated guardian route so the public assertions cannot pass vacuously)
- E2E-mocked: `frontend/e2e/visual.spec.ts` (the landing footer that links to both pages is inside the landing-page visual baseline)
- **Gap**: no `e2e-real`, `e2e-staging`, or `e2e-prod` coverage, and no test asserts the pages resolve over HTTP for a signed-out client against a deployed environment. That is the assertion KWS actually depends on; the component tier proves the components need no session, not that the deployed URL answers.

## Guardian: invite a co-parent (self-serve)

The guardian's own way to add a second adult to the family, from the guardian
console, without an app admin doing it for them. It is the same
invite-a-guardian outcome as the admin WS-J flow below, reached by the family
itself.

- Component: `frontend/src/guardian/InviteCoParentSection.test.tsx` (the email field and submit control render; the happy path posts exactly `{ email }` to `/v1/me/family/invite-guardian` and confirms with a `role="status"` message; the field is cleared afterwards so the form is ready for a second invite; a 409 gets its own "already a pending invite" message rather than the generic one, and any other failure gets the generic server-side message; the in-flight state shows a disabled "Sending invite" button whose label, not its disabled attribute, is what proves the request finished, since the cleared email field independently disables the button; the submit control stays disabled until an email is entered; and editing the email again clears a stale error so a retry is not shown a previous attempt's alert)
- **Gap**: no E2E coverage at any tier yet. The admin-initiated equivalent is covered end to end by `frontend/e2e/admin-user-management.spec.ts` under WS-J below.

## Guardian: review and edit own family's story (G6)

The guardian-facing half of review, at `/guardian/review/:storybookId`. It is
deliberately narrower than the admin review page below: the guardian reads
their own family's story through the review-surface GET and may edit passages,
but holds none of the approve/publish authority. The passage-edit modules
(`passageEditApi.ts`, `usePassageEdit.ts`, `ReviewPassage.tsx`) live under
`guardian/` and are shared with the admin review page.

- E2E-mocked: `frontend/e2e/review-edit.spec.ts` (the passage-edit `PATCH` contract, asserted at the network layer from the review detail; see the admin section below)
- Component: `frontend/src/guardian/GuardianReviewDetailPage.test.tsx` (the route's authority boundary and edit surface: it loads the requesting family's own story via the review-surface GET, renders no Approve, Send Back, Archive, cover-generation, or version-compare control, links back to My Requests, and refuses another family's story with a clear message plus a way back. Its passage-edit block covers opening the dialog prefilled with the passage body and choice labels, saving and refreshing the surface from the response, rendering inline rule messages on a 422 gate failure while leaving the blob unchanged, editing disabled once the story is published, and a `needs_revision` status hint with editing still enabled)
- Component (shared passage-edit modules): `frontend/src/guardian/passageEditApi.test.ts` (the `PATCH /v1/storybooks/:id/versions/:v/nodes/:nodeId` request shape, `choice_labels` sent alongside `body` when both are supplied, URL-encoding of a node id that needs it, and `asGateFailure` extracting findings from a 422 gate-failure body while returning null for a non-422, a 422 with no `details.findings` such as FastAPI's own request-body validation, and a non-axios error) and `frontend/src/guardian/usePassageEdit.test.ts` (the hook's state machine: `editingDisabled` before the surface loads and for a published surface versus enabled for `in_review`/`needs_revision`; opening is a no-op before load or for a node id absent from the blob; the dialog prefills body and choices and updates only the matching choice label; saving is a no-op with no dialog open or if the surface became unavailable after it opened; a successful save feeds the refreshed surface up and closes the dialog; a 422 surfaces gate findings without closing; a non-gate failure surfaces a generic error; and close resets error and gate-finding state)
- **Gap**: no `e2e-real`, `e2e-staging`, or `e2e-prod` coverage yet; the route needs a real storybook id, the same constraint that keeps `/admin/review/:id` out of the staging and prod smokes.

## Admin: review queue (single story review)

- E2E-mocked: `frontend/e2e/guardian-review.spec.ts`, `frontend/e2e/review-edit.spec.ts` (passage-edit save: PATCHes a reachable node's body + choice_labels and an unreachable/orphan node's body-only from the review detail, asserting the exact `PATCH /v1/storybooks/{id}/versions/{v}/nodes/{node}` contract at the network layer), `frontend/e2e/guardian-console.spec.ts` (navigation), `frontend/e2e/naive-user/naive-admin-misuse.spec.ts`, `frontend/e2e/naive-user/naive-misuse-shared.spec.ts`
- E2E-real: `frontend/e2e-real/approval-flow.spec.ts`
- Component: `frontend/src/admin/ReviewDetailPage.test.tsx`, `frontend/src/admin/AdminConsolePage.test.tsx` (links into it), `frontend/src/guardian/reviewApi.test.ts`, `frontend/src/guardian/coverApi.test.ts` (cover generation on review page), `frontend/src/admin/rescreenApi.test.ts` (the re-screen trigger's request contract: `triggerForStorybook` scopes the sweep to a single id by posting `{ storybook_ids: [id] }` to `/v1/admin/rescreen` and returns the summary unchanged, and a backend rejection such as a 403 propagates to the caller rather than being swallowed into a fake success). The passage-edit modules this page uses now live under `guardian/` and are shared with the guardian review route; their tests are listed in the guardian section below.
- **Gap**: no E2E-staging coverage, `/admin/review/:id` needs a real storybook id and is excluded from the render-only staging smoke for the same reason `e2e-prod` excludes it. The passage-edit E2E is mocked-only for now; promote alongside `approval-flow.spec.ts` when the real tier grows a review-edit journey.

## Admin: cover generation (A16)

- E2E-mocked: `frontend/e2e/admin-review-cover.spec.ts` (the "Generate cover" button on `/admin/review/:id` is present, a status GET seeds its state on mount, clicking it fires the mocked POST to `/storybooks/:id/versions/:version/cover`, and the button shows a "Generating cover…" pending state)
- Component: `frontend/src/admin/useCoverGeneration.test.ts`, `frontend/src/guardian/coverApi.test.ts` (`coverApi.ts` lives under `guardian/` but is used only by the admin review page)
- **Gap**: no `e2e-real`, `e2e-staging`, or `e2e-prod` coverage yet.

## Admin: cross-family request queue

- E2E-mocked: `frontend/e2e/guardian-console.spec.ts`, `frontend/e2e/naive-user/naive-admin-misuse.spec.ts`
- E2E-real: `frontend/e2e-real/approval-flow.spec.ts`
- E2E-staging: `frontend/e2e-staging/guardian-admin-smoke.spec.ts` (render only)
- E2E-prod: `frontend/e2e-prod/guardian-admin-smoke.spec.ts` (render only)
- Component: `frontend/src/admin/AdminConsolePage.test.tsx`, `frontend/src/admin/AdminRequestsPage.test.tsx`, `frontend/src/guardian/RequestStoryForm.test.tsx` (admin-mode family selector), `frontend/src/guardian/authoredRequestApi.test.ts` (listFamilies)

## Admin: moderation dashboard/thresholds

- E2E-mocked: `frontend/e2e/moderation.spec.ts` (add/remove a threshold override, save the admin noise floor, apply a dashboard suggestion end to end against the routed app). Verified against a real browser and passing (2026-07-16).
- E2E-real: `frontend/e2e-real/moderation-real.spec.ts` (add/remove a real threshold override, update and reload-persist the real noise floor, confirm the real dashboard genuinely has no qualifying suggestions on the current seed data)
- E2E-staging: `frontend/e2e-staging/guardian-admin-smoke.spec.ts` (render smoke only)
- E2E-prod: `frontend/e2e-prod/guardian-admin-smoke.spec.ts` (render smoke only)
- Component: `frontend/src/admin/ModerationDashboardPage.test.tsx`, `frontend/src/admin/ModerationThresholdsPage.test.tsx`, `frontend/src/admin/AdminShell.test.tsx` (nav link only)
- **Remaining gap**: `moderation-real.spec.ts` deliberately does NOT cover the "a suggestion actually appears" path. Per `src/cyo_adventure/moderation/insights.py`, that needs at least 5 decided (released/sent-back) versions with an overridable finding in the same (age_band, category); neither `scripts/seed_dev_data.py` nor `seed_staging.py` create that corpus, so proving it against a real backend means seeding 5+ qualifying storybook versions first, a separate, larger addition (see `tests/integration/test_moderation_dashboard_api.py`'s `_seed_high_override_corpus` for the exact shape that data needs to take). Not attempted in this pass.

## Admin: provider allowlist management

Built 2026-07-16, closing the gap this matrix previously flagged as "no coverage found, no UI exists." A 2026-07-16 audit confirmed the backend (full CRUD + audit trail, `src/cyo_adventure/api/provider_allowlist.py`, `tests/integration/test_provider_allowlist_api.py`) had no frontend page, and no ADR/roadmap/tech-spec ever explicitly deferred one; `AllowlistCreateBody.display_name`'s docstring ("for a future admin UI") implied it was anticipated. `ProviderAllowlistPage.tsx` is a general settings page (global, not tied to any one story): add/enable/disable/remove `(provider, model_id)` rows.

- E2E-mocked: `frontend/e2e/provider-allowlist.spec.ts` (add, disable, remove a real row against the routed app)
- E2E-real: `frontend/e2e-real/provider-allowlist-real.spec.ts` (an admin adds, disables, and removes a real `(provider, model_id)` row through the real `POST`/`PUT`/`DELETE /v1/admin/provider-allowlist` endpoints, each state persisting across reload; plus a plain guardian visiting the page is redirected back to the guardian console by the real `/v1/me` role)
- Component: `frontend/src/admin/ProviderAllowlistPage.test.tsx`, `frontend/src/admin/providerAllowlistApi.test.ts`
- **Gap**: no `e2e-staging` or `e2e-prod` coverage yet.

## Admin: authoring plan (method/mechanism/model selection)

New journey, not previously in this matrix: the step between a guardian/admin
approving a story *request* (`StoryRequestQueue`, which sets age_band/length/
narrative_style) and generation actually starting. `POST /story-requests/{id}/
authoring-plan` had a full backend implementation and a working generated
client method but **no frontend UI at all** until this feature landed
(2026-07-16 admin-role audit); the only way to advance an approved request
into generation was a raw API call. `AuthoringQueuePage.tsx` lists approved
requests; `AuthoringPlanDialog.tsx` is the admin's method/mechanism/model
picker, reading available models from the provider allowlist above and
showing the request's already-locked-in age_band/length/narrative_style as
read-only context (they cannot be re-edited at this step, matching the
2026-07-16 audit's finding that no second edit point exists anywhere).

- E2E-mocked: `frontend/e2e/authoring-queue.spec.ts` (skill-mechanism plan, automated-provider plan constrained to the allowlist, fresh-generation forcing automated-provider)
- E2E-real: `frontend/e2e-real/authoring-plan-real.spec.ts` (both mechanisms against a freshly submitted-and-approved real request; caught a real bug live, see below)
- Component: `frontend/src/admin/AuthoringQueuePage.test.tsx`, `frontend/src/admin/AuthoringPlanDialog.test.tsx`, `frontend/src/admin/authoringPlanApi.test.ts`
- **Real bug found and fixed during this build**: `prep_model` is unconstrained free text for `mechanism='automated_provider'` but is validated against a fixed set of Claude Code session model aliases (`SKILL_MECHANISM_MODELS`) for `mechanism='skill'`; a free-text field for both would have shipped a confusing live 422 ("prep_model 'x' is not a recognized Claude Code session model") for any real admin using the skill path. Caught only by running `e2e-real/authoring-plan-real.spec.ts` against a real backend, not by any mocked test. Fixed by rendering a constrained `<select>` for `mechanism='skill'` and free text only for `mechanism='automated_provider'`.
- **Gap**: no `e2e-staging` or `e2e-prod` coverage yet. `review_stage1_model`/`review_stage2_model` (optional Stage 1/2 overrides, skeleton_fill only) are deliberately not exposed in the UI at all, a v1 scoping decision, not a test gap.

## Admin: user / profile / family management (WS-J)

- E2E-mocked: `frontend/e2e/admin-user-management.spec.ts` (an admin reaches the console from the admin nav, switches to the Families tab and sees member counts, invites a guardian and confirms both the POST body and the roster refresh, and a plain guardian visiting `/admin/users` is redirected back to the guardian console)
- E2E-real: `frontend/e2e-real/admin-management-real.spec.ts` (Kids tab only, the highest-value real write in this journey per the work order: an admin creates, edits, and deactivates a real profile in another family through `POST`/`PATCH /v1/admin/profiles`, each state persisting across reload; plus a plain guardian visiting `/admin/users` is redirected back to the guardian console by the real `/v1/me` role. There is no delete route, so a real run leaves one deactivated profile behind by design; Users/Families/Connections tabs are not covered here)
- Component: `frontend/src/admin/UserManagementPage.test.tsx`, `frontend/src/admin/UsersTab.test.tsx`, `frontend/src/admin/FamiliesTab.test.tsx`, `frontend/src/admin/ConnectionsTab.test.tsx`, `frontend/src/admin/KidsTab.test.tsx`, `frontend/src/admin/userManagementApi.test.ts`
- **Gap**: no `e2e-staging` or `e2e-prod` coverage yet.

## Admin: audit log, master library, and version-compare (read-heavy surfaces)

Lower-exposure admin read surfaces that had component coverage but no
browser-level journey until the 2026-07-22 audit backfill: the audit log
(filter + paging), the admin master library (lifecycle-status filter), and the
review version-compare panel (`ReviewCompare`, reachable only from the review
detail when a storybook has more than one version).

- E2E-mocked: `frontend/e2e/admin-read-heavy.spec.ts` (audit-log event-kind filter refetches `GET /v1/admin/audit?kind=...` and next-page refetches with `offset=50`; admin-library lifecycle filter refetches `GET /v1/admin/storybooks?status=archived`; the version-compare panel loads the previous version via `GET /v1/storybooks/{id}/review?version=...` and renders the diff), `frontend/e2e/admin-audit.spec.ts` (the audit log at browser level plus its access control: a plain guardian visiting `/admin/audit` is redirected AND no request reaches the admin audit endpoint, and an unauthenticated visit redirects to guardian login)
- Component: `frontend/src/admin/AuditPage.test.tsx`, `frontend/src/admin/auditApi.test.ts`, `frontend/src/admin/AdminLibraryPage.test.tsx`, `frontend/src/admin/adminLibraryApi.test.ts`, `frontend/src/admin/ReviewCompare.test.tsx` (owns the loading/error/404-unavailable compare branches the E2E leaves to it)
- **Gap**: no `e2e-real`, `e2e-staging`, or `e2e-prod` coverage yet; these are read-only surfaces, so exposure is low. Access control (non-admin and unauthenticated) is now covered at the mocked tier by `admin-audit.spec.ts`.

## Kid: profile picker

- E2E-mocked: `frontend/e2e/device-authorization.spec.ts`, `frontend/e2e/landing.spec.ts`, `frontend/e2e/profiles.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts`
- E2E-real: `frontend/e2e-real/kid-reads.spec.ts`
- Component: `frontend/src/kid/ProfilePickerPage.test.tsx` (incl. PIN gate), `frontend/src/kid/KidNav.test.tsx`, `frontend/src/kid/KidShell.test.tsx`, `frontend/src/kid/childSessionApi.test.ts`, `frontend/src/kid/storyStatusApi.test.ts` (W1.4 "new story!" pill adapter: normal, malformed, and error responses all degrade to no pills), `frontend/src/profiles/AvatarCircle.test.tsx`, `frontend/src/profiles/profilesApi.test.ts`
- Integration: `frontend/src/test/App.test.tsx`

## Kid: persistent character (ADR-028: first-run creation, switching, seeded read)

The once-per-profile character a child makes on their first library visit, keeps
across every book, and can switch between afterwards. The character's
`seed_var_state` is computed server-side and threaded into the reader as the
read's starting variables; the client never derives a seed of its own.

- Component: `frontend/src/characters/CharacterCreator.test.tsx` (the first-run
  form: the happy-path create call and its exact request body, the literal
  six-item archetype roster in backend wire order, the three input guards
  (missing name including whitespace-only, missing role, missing look) each
  refusing before any API call, the client-side 32-character bound, the server's
  422 naming-violation message surfaced verbatim rather than replaced, both
  directions of the non-422 failure fork (401/403 says ask a grown-up, 500 and a
  transport failure offer a retry), the per-look accessible name carrying the
  color rather than the emoji's platform-chosen announcement, the name field's
  `aria-invalid`/`aria-describedby` association appearing and clearing with the
  error, and no state write after an unmount mid-submit),
  `frontend/src/characters/CharacterPicker.test.tsx` (the switcher: the active
  tile reads pressed and the others do not, choosing another calls activate and
  flips the selection in place with no reload, an empty profile falls through to
  the creator rather than an empty grid, the tiles are a plain `aria-pressed`
  list and NOT an ARIA radiogroup (which would promise arrow-key navigation this
  component does not implement), the 401/403 "find your grown-up" state offering
  no retry, the load-failure state whose "Try again" re-issues the GET, and an
  activate rejection that shows the retry message and leaves the tile enabled
  rather than stuck busy), `frontend/src/characters/characterApi.test.ts` (the
  `/v1/characters` adapter's request shape for all six routes, plus the two
  drift guards on the shared catalogs: the archetype roster order is the
  backend's stored numeric code, and every look id has both a swatch and a
  distinct spoken label), `frontend/src/characters/useActiveCharacter.test.ts`
  (which character is active, and the discrimination that matters most: an
  unparseable or wrong-shaped response resolves to `'error'`, never to `'none'`,
  because the first-run gate treats `'none'` as "safe to show the creator"),
  `frontend/src/kid/KidShell.test.tsx` (the first-run gate itself, mounted
  through the shell: `'none'` shows the creator AND withholds the library
  Outlet, `'ready'` renders the Outlet, and `'loading'`/`'error'` also render it,
  pinning the deliberate fail-safe; plus the single per-route lookup handed down
  through the Outlet context),
  `frontend/src/library/LibraryPage.test.tsx` (the active-character strip's two
  sources: it reuses the shell's resolved lookup with no fetch of its own, and
  falls back to fetching one when mounted outside KidShell, as the guardian
  preview-as-child route does), `frontend/src/reader/characterSeed.test.ts` (the
  read's starting variables: the seed is read off the server-computed
  `seed_var_state`, never derived client-side, and every lookup failure opens
  the read unseeded rather than blocking it)
- **Gap**: no E2E tier at any level. No catalog book declares a character
  envelope yet (deliberate, per ADR-028), so no seeded read exists to drive
  end-to-end; the creation and switching flows themselves are E2E-testable today
  and are not yet covered.

## Kid: browse library

- E2E-mocked: `frontend/e2e/library.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts`, `frontend/e2e/story-requests-kid.spec.ts`
- E2E-real: `frontend/e2e-real/kid-reads.spec.ts`, `frontend/e2e-real/naive-kid-misuse-real.spec.ts` (cross-family 403)
- E2E-staging: `frontend/e2e-staging/kid-library-smoke.spec.ts` (populated-library render, via mint/revoke device grant), `frontend/e2e-staging/moderation-qa-invisibility.spec.ts` (the moderation QA corpus is present in the admin master library and unpublished, and absent from both the kid library API response and the rendered library, via mint/revoke device grant)
- E2E-prod: `frontend/e2e-prod/kid-device-grant.spec.ts` (empty-state render)
- Component: `frontend/src/library/LibraryPage.test.tsx`, `frontend/src/library/BookCard.test.tsx`, `frontend/src/library/pickHero.test.ts`, `frontend/src/library/libraryApi.test.ts`, `frontend/src/library/RequestStory.test.tsx`, `frontend/src/library/storyRequestApi.test.ts`, `frontend/src/library/bookCardUtils.test.ts` (the "New" badge's pure predicate, `isRecentlyPublished`: inside and exactly at the `NEW_BADGE_WINDOW_MS` edge is new, one second past it is not, and every not-new fallback is pinned explicitly rather than left to chance, a null `published_at`, the field absent entirely on an offline-cached item that predates it, a malformed timestamp, and a future timestamp as clock-skew defense)
- Integration: `frontend/src/test/App.test.tsx`

## Kid: progress, badges, and weekly ring (K21/K22/K23, W3.2/W3.4)

- Component: `frontend/src/kid/WeeklyRing.test.tsx` (band-default resolution, once-per-week
  celebration, K14 no-negative-states), `frontend/src/kid/BadgeCase.test.tsx` (earned vs locked
  rendering), `frontend/src/kid/badgeCatalog.test.ts` (drift guard against the backend badge
  catalog), `frontend/src/kid/progressApi.test.ts` (adapter shape degradation to safe defaults),
  `frontend/src/library/EndingsGallery.test.tsx` (found cards, hidden silhouettes, large-M
  milestone mode, no negative framing), `frontend/src/reader/ReaderPage.badgeToast.test.tsx`
  (unlock diff + IndexedDB seen-state dedupe), `frontend/src/reader/BadgeUnlockToast.test.tsx`
  (auto-dismiss, manual close, disabled auto-dismiss, unmount cleanup),
  `frontend/src/reader/EndingsGalleryButton.test.tsx` (opens only after the fetch settles,
  in-flight disable, failure logs profile context and degrades to the empty state),
  `frontend/src/kid/kidMotion.test.ts` (stylesheet-text assertions that both reduce-motion
  paths, the OS preference and the guardian per-profile flag, still the weekly ring's
  progress transition, its celebrate animation, and the picker pill; jsdom never applies
  these rules, so no rendering test can cover them)
- Integration: `frontend/src/test/App.test.tsx`

## Kid: read a story (reader page, choices, endings)

- E2E-mocked: `frontend/e2e/reader.spec.ts`, `frontend/e2e/reader-conflict.spec.ts`, `frontend/e2e/reader-reload-resume.spec.ts`, `frontend/e2e/series-continue.spec.ts`
- E2E-real: `frontend/e2e-real/kid-reads.spec.ts`, `frontend/e2e-real/series-continue-real.spec.ts`
- Component: `frontend/src/reader/Reader.test.tsx`, `frontend/src/reader/ReaderPage.test.tsx` (largest suite), `frontend/src/reader/ReaderRoute.test.tsx`, `frontend/src/reader/ReaderChrome.test.tsx`, `frontend/src/reader/ReaderLeave.test.tsx`, `frontend/src/reader/BackToLibrary.test.tsx`, `frontend/src/reader/BookmarksButton.test.tsx` (the bookmarks panel: save/load/delete a slot, the 10-slot ceiling disabling Save, and a corrupted `save_slots` entry being silently excluded rather than crashing the list), `frontend/src/reader/dialogs.test.tsx`, `frontend/src/reader/readerProgress.test.ts`, `frontend/src/player/engine.test.ts` (bookmark engine functions: `canSaveBookmark`, `saveBookmark`, `loadBookmark`, `deleteBookmark`, `listBookmarks`), `frontend/src/player/evaluator.test.ts`, `frontend/src/player/machine.test.ts`, `frontend/src/player/stops.test.ts` (ADR-026 rendered-stop composition, shared `stop_traces.json` corpus with the Python engine), `frontend/src/api/readerApi.test.ts`, `frontend/src/reader/readerSoundEvents.test.ts`, `frontend/src/reader/soundPreference.test.ts`, `frontend/src/reader/sounds.test.ts` (W4.2 placeholder SFX: mute logic, reduce-motion quiet default, event bus isolation), `frontend/src/reader/useReadingTimeAccumulator.test.ts` (K23 client half: 90s idle window, visibility gating, read-aloud counts as active)
- Integration: `frontend/src/test/App.test.tsx`

## Kid: personalized story rendering (ADR-023 P6/P7, flag-gated)

- Component: `frontend/src/player/personalization.test.ts` (the pure sentinel resolver, `resolvePersonalization`: value substitution for bound slots including every-occurrence replacement, generic-word fallback for a missing value/binding/empty string, the unconditional strip that runs with no payload at all (the flag-off path), idempotence on resolved text, malformed-marker stripping so a near-miss never reaches a child, the value-free once-per-call strip warning, and rejection of a payload whose `sentinel_pattern` differs from the pinned constant), `frontend/src/api/personalizationApi.test.ts` (the values fetch adapter for `GET /v1/storybooks/{id}/personalization-values`: payload pass-through, and null on any HTTP or transport failure so the reader still renders generic), `frontend/src/reader/DedicationOverlay.test.tsx` (opening-screen dedication overlay: full template with both halves, name-only fallback, and the render-nothing branches for no name, no payload, and a ring-2 payload)
- **Gap**: no E2E tier at any level yet; `VITE_FEATURE_PERSONALIZATION` is off everywhere (gate G3, Task D1), so E2E coverage lands with the flag's first enablement.

## Kid: read-aloud (K7)

- E2E-mocked: `frontend/e2e/kid-read-aloud.spec.ts` (the speaker toggle appears only for a profile with `tts_enabled: true`, picked through the real picker flow rather than a deep link, since the flag rides the picker's profiles fetch; tapping it toggles a "speaking" state, and both a re-tap and a choice navigation cancel speech; a fake `speechSynthesis` stands in for headless Chromium's real one, which has no installed voices)
- E2E-real: `frontend/e2e-real/kid-read-aloud-real.spec.ts` (the `tts_enabled` gate is real: a guardian `PATCH /v1/profiles/{id}` turns it on, then the kid picker's real `GET /v1/profiles` reads it back and threads it into the reader as the `ttsEnabled` prop; the toggle itself is client-only, Web Speech, with only its own speak/stop state asserted, not audio output, and `window.speechSynthesis.speak` stubbed to remove a real timing race between the browser's own `onend` and the test's stop click)
- Component: `frontend/src/kid/readAloudPreference.test.ts`, `frontend/src/reader/useReadAloud.test.ts`, `frontend/src/reader/readAloudHighlight.test.ts` (the follow-along word highlight's pure range math, `wordRangeAtIndex`: the word at a `boundary` event's `charIndex`, the forward walk when an engine reports the boundary a character early and lands in whitespace, multi-paragraph text across a blank line, and the null-returning guards for negative, non-finite, past-the-end, and trailing-whitespace indices)
- **Gap**: no `e2e-staging` or `e2e-prod` coverage yet; no tier asserts real audio output, the real tier above exercises the toggle and the real `tts_enabled` gate but stubs the speech call itself.

## Kid: flag a passage (K15)

- E2E-mocked: `frontend/e2e/reader-flag.spec.ts` ("Tell a grown-up" posts a structured `reason` (no free-text field) and shows the kid-language confirmation; a 409 cap response shows the gentle "You've told us a lot already" message; the button is hidden entirely without a valid child session)
- E2E-real: `frontend/e2e-real/kid-flag-real.spec.ts` (a kid submits a real structured flag through `POST /v1/flags`, asserted at the network layer as a `201` with `reason: scared_me`, then re-fetched via the real admin `GET /v1/admin/flags` to confirm it persisted open server-side rather than only in the POST's own response body; an `afterEach` resolves the flag it created so `MAX_OPEN_FLAGS_PER_PROFILE` is never exhausted by repeat runs)
- Component: `frontend/src/reader/FlagButton.test.tsx`, `frontend/src/guardian/FlagBadge.test.tsx`
- **Gap**: no `e2e-staging` or `e2e-prod` coverage yet.

## Kid: go back / undo (K5)

- E2E-mocked: `frontend/e2e/reader-go-back.spec.ts` ("Go back" is absent at the start node, appears after a choice, and undoing past a state-gated choice (`c_dark_passage`, gated on `has_lantern`) still offers that choice correctly afterward, proving the engine replays the recorded path rather than corrupting state)
- E2E-real: `frontend/e2e-real/kid-go-back-real.spec.ts` (after two real choices, "Go back" reverts the reader to the prior node and the real `PUT /v1/reading-state/{profile_id}/{storybook_id}` this triggers persists the reverted `current_node`/`path`, confirmed not just via the PUT's own response but via an independent guardian-authorized `GET` re-fetch of the same row, proving the server, not only client state, holds the reverted position)
- Component: `frontend/src/reader/BackToLibrary.test.tsx`, `frontend/src/player/engine.test.ts` (go-back is a bounded replay computation in the player engine)
- **Gap**: no `e2e-staging` or `e2e-prod` coverage yet.
- **Gap (F-6c), registered but deliberately skipped**:
  `frontend/e2e-real/kid-go-back-gated-real.spec.ts` is a single
  `test.skip` with no implementation, committed so the missing case is tracked
  in this matrix rather than forgotten. It does not run and proves nothing
  today. The case it would cover, going back *past a variable-gated choice*
  against the real backend, is blocked on seed data, not on effort: the mocked
  `reader-go-back.spec.ts` covers gated replay against a mocked PUT, and
  `kid-go-back-real.spec.ts` covers real persistence but on "The Tide Pool
  Mystery", which declares no variables at all. Every other seeded story with a
  variable gate is unusable here, "The Clockwork Garden" and "The Bridge
  Builder" are each exclusively owned by a sibling real-backend spec's fixture
  lifecycle (no cross-file ordering guarantee in this tier), and the Ember Trail
  series' only gated choice is reachable solely through a continuation read,
  where `player/engine.ts` fails go-back closed by design. The spec's header
  carries a `TODO(seed)` describing the small dedicated fixture
  `scripts/seed_dev_data.py` needs before it can be implemented.

## Kid: offline reading + sync/conflict resolution

- E2E-mocked: `frontend/e2e/reader.spec.ts` (fully-offline play), `frontend/e2e/reader-conflict.spec.ts`, `frontend/e2e/reader-reload-resume.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts` (reload resume)
- E2E-real: `frontend/e2e-real/offline-conflict-real.spec.ts` (two real `BrowserContext`s race saves on "The Clockwork Garden": device A creates the row, device B resyncs and advances it, device A's next save gets a real 409 resolved via "Keep this device", device B's next gets a real 409 resolved via "Use the newest place"; picked up by the nightly `e2e-real-nightly.yml`), `frontend/e2e-real/offline-online-parity-real.spec.ts` (G3, Phase 7.3: on "The Clockwork Garden", a condition-gated story, the identical five-choice sequence is driven online through the real backend and, in a separate profile, offline through the client player engine then synced; both land on the same final node/path/visit_set/var_state and the same ending, proving offline/online branch parity; each pass also forces a real Python-engine replay of its own choice sequence via the `choice_path` field on the reading-state PUT, so the parity is confirmed cross-engine, not just client-vs-client), `frontend/e2e-real/offline-reconnect-real.spec.ts` (reconnect replay against the real backend: every queued offline choice replays and the server row lands on the expected `current_node`/`var_state`; and a conflict case where a real second device advances the row while device A is offline, so A's stale replay takes a real 409 and never clobbers it. Runs on the nightly `real-backend` project, not on PRs)
- Component: `frontend/src/offline/db.test.ts`, `frontend/src/offline/sync.test.ts`, `frontend/src/offline/downloadBudget.test.ts` (W4.3 250MB/500MB storage.estimate gate + least-recently-opened eviction + kid-friendly refusal), `frontend/src/offline/deviceId.test.ts` (the client-generated persistent device id: minted once, read back stable across calls, and survives a `localStorage` round-trip; the G15 download-report identity), `frontend/src/offline/readingTimeSync.test.ts` (K23 idempotent day-bucket flush: frozen flush_id/delta pairs, offline accrual), `frontend/src/offline/revocation.test.ts` (offline-copy revocation reconcile: shared-blob refcounting, cross-profile isolation, queue-drop, never-purge-on-failed-fetch, and the documented mid-read latency window), `frontend/src/reader/ReaderPage.test.tsx` (conflict dialog resolution paths), `frontend/src/reader/ReaderRoute.test.tsx` (replay-reconciliation suite), `frontend/src/reader/dialogs.test.tsx` (ConflictDialog UI), `frontend/src/hooks/useReplayOnReconnect.test.ts`, `frontend/src/hooks/useOnlineStatus.test.ts`, `frontend/src/library/LibraryPage.test.tsx` (the reconcile call-site: fires only on the success branch, re-fires on reconnect, logs a reconcile rejection)
- **Gap**: no `e2e-staging` or `e2e-prod` coverage of conflict/sync against a real backend. Offline-copy revocation (register G8/A5) has a known mid-read latency window: a book pulled server-side is not purged from the device until the next successful library fetch drives a reconcile; closing it needs a revocation push channel or reader-route mid-session revalidation, both out of scope (pinned by the `revocation.test.ts` "mid-read latency window" characterization test).

## Kid: series continuation across storybooks

- E2E-mocked: `frontend/e2e/series-continue.spec.ts`, `frontend/e2e/story-requests-kid.spec.ts` (anchor), `frontend/e2e/story-requests.spec.ts` (series_title prefill)
- E2E-real: `frontend/e2e-real/series-continue-real.spec.ts`
- Component: `frontend/src/reader/ContinueSeries.test.tsx`, `frontend/src/player/series.test.ts`, `frontend/src/library/BookCard.test.tsx`, `frontend/src/library/LibraryPage.test.tsx` (continue-request), `frontend/src/library/RequestStory.test.tsx` (anchor mode), `frontend/src/reader/Reader.test.tsx` (continuation-eligibility gating), `frontend/src/reader/ReaderPage.test.tsx` / `ReaderRoute.test.tsx` (continuation-seed handling), `frontend/src/api/readerApi.test.ts` (`makeFetchSeriesNext`)

## Device authorization flow (kid device pairing)

- E2E-mocked: `frontend/e2e/device-authorization.spec.ts`, `frontend/e2e/landing.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts`, `frontend/e2e/guardian-devices.spec.ts` (the guardian's authorized-device list in the routed app: revoking is gated behind the confirm dialog and fires `DELETE /v1/device-grants/{id}` for that device only, cancelling sends nothing, and an unauthenticated visit redirects to guardian login)
- E2E-real: `frontend/e2e-real/kid-reads.spec.ts`, `frontend/e2e-real/naive-kid-misuse-real.spec.ts`, `frontend/e2e-real/series-continue-real.spec.ts`, `frontend/e2e-real/real-stack.ts` (helper)
- E2E-staging: `frontend/e2e-staging/kid-library-smoke.spec.ts` (one of two grant-writing staging specs, with `afterAll` cleanup, mirroring the prod pattern; `moderation-qa-invisibility.spec.ts` runs the same reversible mint/revoke pattern)
- E2E-prod: `frontend/e2e-prod/kid-device-grant.spec.ts` (the one prod spec that writes, with `afterAll` cleanup)
- Component: `frontend/src/auth/DeviceAuthorizedRoute.test.tsx`, `frontend/src/auth/deviceGrant.test.ts`, `frontend/src/auth/deviceGrantApi.test.ts`, `frontend/src/landing/LandingPage.test.tsx`, `frontend/src/guardian/ConsolePage.test.tsx` (mint/re-authorize/revoke), `frontend/src/guardian/LoginPage.test.tsx` (authorize-device intent), `frontend/src/offline/db.test.ts` (device-grant mirror + migration), `frontend/src/hooks/useApi.test.ts` (device-grant bearer selection/clearing), `frontend/src/guardian/DevicesPage.test.tsx` (the guardian's authorized-device list: empty state, a granted device rendered with its label and grant date, the "Unnamed device" fallback for a null label, and the "This device" marker driven by matching the browser's own stored `device_grant` id so only the matching row is marked. Revoking is gated behind a confirm dialog, the `DELETE /v1/device-grants/{id}` fires only on confirm and the row then disappears, cancelling leaves the list untouched with no request sent, and a failed revoke shows a row-level error while keeping the device listed and its button re-enabled. Also pins the revocation copy against real backend behavior: `api/deps.py::_child_principal` does no database round-trip, so an already-minted child session survives revocation for the rest of its 12-hour TTL, and the page must not claim the cut-off happens on the next reconnect. The same suite also covers the page's G15 downloads section: grouped-by-device rendering, the empty/loading/error states fetched independently of the device-grant list, and each row's profile name/book title/last-confirmed display), `frontend/src/guardian/deviceDownloadsApi.test.ts` (the `GET /v1/device-downloads` adapter backing that section: payload pass-through and null on any HTTP or transport failure)
- Integration: `frontend/src/test/App.test.tsx`

## Ratings (star rating on completed stories)

- E2E-mocked: `frontend/e2e/library.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts` (double-rating keeps latest)
- E2E-real: `frontend/e2e-real/ratings-real.spec.ts` (tap a star against the real backend, reload, confirm the rating persisted server-side rather than only in client state)
- Component: `frontend/src/library/StarRating.test.tsx`, `frontend/src/library/LibraryPage.test.tsx` (rate POST + optimistic/revert), `frontend/src/library/libraryApi.test.ts` (`rate()`)
- **Remaining gap**: still no `e2e-staging` or `e2e-prod` coverage; low priority given the real-backend and component coverage now in place.

---

## Known gaps (as of this audit)

Gaps 1, 2, 4, and 6 below were closed (fully or per-tier) in follow-up
passes; entries are kept (marked Closed) rather than deleted so the audit
trail of what was fixed and when is preserved, per the policy at the bottom
of this file.

1. **Screening/anchoring** — Closed. `StoryRequestQueue.test.tsx` now gives
   the shared anchored-request component its own dedicated unit coverage
   (see the journey section above); there was never a separate frontend
   screening/anchoring module to test, that logic lives server-side.
2. **Moderation dashboard/thresholds** — Closed for the mocked tier
   (`frontend/e2e/moderation.spec.ts`, adding/removing a threshold
   override, saving the noise floor, applying a dashboard suggestion,
   verified against a real browser) and for the real-backend tier
   (`frontend/e2e-real/moderation-real.spec.ts`, same CRUD workflow against
   the live API, verified twice for idempotency). See that journey's
   section above for the one path still not covered: a real suggestion
   actually appearing, which needs a bigger seed-data addition.
3. **Provider allowlist management** — Closed. Built `ProviderAllowlistPage.tsx`
   (general CRUD settings page) plus, since the real user need turned out to
   span two related gaps, the previously-nonexistent `AuthoringQueuePage.tsx`/
   `AuthoringPlanDialog.tsx` (the actual per-story model picker that reads
   from this allowlist). See the two journey sections above for full detail,
   including a real bug (a confusing 422 for the skill mechanism) caught only
   by the real-backend E2E spec and fixed before shipping.
4. **Ratings** — Closed for the real-backend tier.
   `frontend/e2e-real/ratings-real.spec.ts` now confirms a tapped rating
   survives a reload against the real backend. Still no `e2e-staging` or
   `e2e-prod` coverage; low priority.
5. **The E2E-staging tier is smoke-only, not full-journey.** It covers only
   render checks (`guardian-admin-smoke.spec.ts`) and one populated-library
   check via device grant (`kid-library-smoke.spec.ts`); it does not
   exercise intake, screening, approval, assignments, or moderation
   workflows end to end the way `e2e-real` does locally. There is also still
   no `dev`-tier environment (see `docs/testing/README.md`); that requires a
   frontend deploy pipeline this repo does not own. Not addressed in this
   pass.
6. **Offline sync/conflict resolution** — Closed for the real-backend tier.
   `frontend/e2e-real/offline-conflict-real.spec.ts` races two genuine
   `BrowserContext`s ("device A" and "device B") against a real backend on
   "The Clockwork Garden": device A opens first and creates the real
   reading-state row; device B opens second, resyncs onto that row, and
   advances it with a real choice; device A's next save then gets a real
   409, resolved via "Keep this device" (rebases A's stale choice and wins);
   device B's next save then gets a real 409 of its own, resolved via "Use
   the newest place" (adopts the server row). No route mocks: every save is
   a genuine `PUT /api/v1/reading-state/{profile_id}/{storybook_id}` against
   uvicorn. The spec is picked up by the nightly `e2e-real-nightly.yml`
   workflow, not the PR path, per the flakiness guidance in the handoff doc
   below. A 2026-07-22 `toPutPayload` whitelist fix in
   `frontend/src/offline/sync.ts` (send only the fields the PUT body's
   `extra="forbid"` schema accepts, instead of echoing back server-View-only
   fields picked up on cross-device resync) was needed to make the spec pass
   4/4; before that fix a resynced save 422'd. Staging and production
   conflict coverage remain genuinely absent. Production is explicitly out
   of scope: this check works by deliberately provoking a real 409, which
   means creating conflicting reading-state on a live system, and
   `frontend/e2e-prod/` is otherwise strictly non-destructive (the one narrow,
   self-cleaning device-grant mint/revoke in `kid-device-grant.spec.ts` is its
   only write). Racing two devices against production reading-state is a
   materially different risk profile and needs a deliberate team decision, not
   a unilateral addition; staging remains fair game. That reasoning, and the
   original two-BrowserContext recipe this spec implements, came from
   `handoff-offline-conflict-real-backend-2026-07-16.md`, retired in PR #444
   and recoverable via
   `git show 4afe490~1:docs/planning/handoff-offline-conflict-real-backend-2026-07-16.md`.

`#ASSUME: external-resources: gaps 2, 4, and (if attempted) 6 above were
authored without access to a running browser or a live backend/Postgres
instance in the environment that wrote them, only tsc -b, ESLint, and
playwright --list verified them. #VERIFY: run each new spec for real (CI
or a local npm run test:e2e / test:e2e:real) before trusting it as
proven, and fix on sight if the live run disagrees with what static
analysis could check.`

## Cross-cutting component and utility tests

These Vitest suites cover shared widgets, hooks, and infrastructure that are
not tied to a single user journey above. They are listed here so the coverage
matrix drift-guard (`scripts/check_coverage_matrix.py`) accounts for every
`frontend/src/**/*.test.{ts,tsx}` file; journey-specific component tests live
in their journey sections instead.

- Guardian widgets: `frontend/src/guardian/BudgetBanner.test.tsx`,
  `frontend/src/guardian/budgetApi.test.ts`,
  `frontend/src/guardian/StoryStructureSummary.test.tsx`,
  `frontend/src/guardian/storyRequestOptions.test.ts`
- Auth/session utilities: `frontend/src/auth/childSession.test.ts`
- Library display: `frontend/src/library/EndingsBadge.test.tsx`,
  `frontend/src/library/RecommendationChip.test.tsx`,
  `frontend/src/library/coverPalette.test.ts`,
  `frontend/src/library/recommendationsApi.test.ts`,
  `frontend/src/library/recommendationsUtils.test.ts`
- Reader controls: `frontend/src/reader/EndingsProgress.test.tsx`,
  `frontend/src/reader/TextSizeControl.test.tsx`,
  `frontend/src/reader/useReaderFontScale.test.ts` (drives the text-size hook's
  own `setLevel` API: each level maps to the scale and `A`/`A+`/`A++` label the
  reader renders, the choice is written through to
  `cyo-reader-font-scale-<profileId>` and survives a real unmount/remount rather
  than only a state update, and the key is profile-scoped so one child's larger
  text does not follow another)
- App shell / infrastructure: `frontend/src/AppErrorBoundary.test.tsx`,
  `frontend/src/routeElements.test.tsx`, `frontend/src/router.test.tsx`
  (structural assertions over the route config with no rendering: which gate
  components stand between the tree root and each leaf URL, carrying a positive
  control on a known-gated route so an ungated-looking result means ungated
  rather than broken detection), `frontend/src/lazyWithReload.test.ts`,
  `frontend/src/observability.test.ts`, `frontend/src/env.test.ts` (table test
  pinning `flagEnabled`'s exact contract, the switch behind every feature flag:
  only the lowercase literal `"true"` is on, so `"TRUE"`/`"True"`/`"1"`/`"yes"`/
  `"on"`/`""`/`undefined` are all off. Guards the `Boolean("false") === true`
  trap the helper exists to dodge, since Vite exposes every env var as a string)
  `frontend/src/notifications/ToastProvider.test.tsx`,
  `frontend/src/hooks/classifyApiError.test.ts`,
  `frontend/src/hooks/logApiError.test.ts`,
  `frontend/src/hooks/usePageTitle.test.ts` (the per-route `document.title`
  hook every routed page calls: the app-name suffix, the `bare` opt-out the
  landing page uses so its title is not doubled, and re-firing when the title
  prop changes. Not tied to one journey because all 29 routed pages share it)
- Theme system (light/dark/system, mounted app-wide at the root via
  ThemeProvider; every surface's chrome renders a ThemeToggle):
  `frontend/src/theme/theme.test.ts` (mode validation, stored-preference
  round-trip, and the localStorage/matchMedia fallbacks) and
  `frontend/src/theme/ThemeProvider.test.tsx` (provider state, `<html
  data-theme>` sync, OS-preference and cross-tab `storage` re-resolution, and
  the ThemeToggle three-way cycle plus its per-mode accessible label)
- Connectivity / offline infrastructure (mobile-web readiness, Phase A):
  `frontend/src/hooks/probeConnectivity.test.ts` (the active fetch-based
  reachability probe behind `useOnlineStatus`: an ok response resolves true, a
  reject or timeout resolves false, and a no-fetch runtime assumes reachable)
  and `frontend/src/offline/persist.test.ts` (`requestPersistentStorage()`: an
  absent Storage API resolves false, and it skips the `persist()` request when
  storage is already persisted)

## Keeping this matrix current

`#ASSUME: data-integrity: this matrix is hand-maintained and will drift as
new spec files are added. #VERIFY: DONE. scripts/check_coverage_matrix.py greps
every file under frontend/e2e/, frontend/e2e-real/, frontend/e2e-staging/,
frontend/e2e-prod/, and frontend/src/**/*.test.{ts,tsx} against this document
and fails if any is not referenced. It runs in the Frontend CI job, so drift is
caught at PR time rather than discovered during an audit.`

When adding a new journey or page, add a section here in the same PR. When
closing one of the gaps above, update its entry to reflect the new coverage
rather than deleting the gap silently, so the audit trail of what was fixed
when is preserved.

This pass (2026-07-22) is exactly that CI check run by hand once: it added
the 8 previously-orphaned specs that existed on disk but were unreferenced
anywhere in this matrix, and corrected gap 6 to reflect its real-backend
closure. A companion action-level verdict for this audit lives at
`docs/testing/action-coverage-robustness-2026-07-22.md`.
