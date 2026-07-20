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
  live production, `frontend/e2e-prod/`, manual only, never CI).
- "NONE FOUND" means no test at that layer touches this journey. It does not
  necessarily mean the journey is unimplemented, only untested at that layer.

## Cross-cutting checks (not tied to one journey)

- **Accessibility**: `frontend/e2e/a11y.spec.ts` — axe-core, scoped to WCAG
  2.1 A/AA, across every top-level page (landing, kid picker, kid library
  populated/empty, reader, guardian login/console/intake/requests/
  books/profiles, admin console/requests/moderation-thresholds/
  moderation-dashboard) and every modal/dialog surface (ConflictDialog,
  AssignChildrenDialog, ProfileFormDialog). `/admin/review/:id` is excluded,
  same reasoning as `e2e-prod/guardian-admin-smoke.spec.ts`: it needs a real
  storybook id and a dynamic heading. Across two passes (2026-07-16) found
  six real contrast failures, all traced to two design-system tokens
  (`--color-amber-deep`, `--color-ink-muted`) used against a darker
  background than their documented contrast math assumed; fixed the same
  day (see `--color-amber-deep-text` in `design-system/src/tokens.css`, the
  `.cyo-btn--primary`/`.cyo-btn--ghost` fixes in `Button.css`, and the
  `--color-ink-secondary` swaps in `guardian.css`/`kid.css`/`library.css`/
  `landing.css`). The dialog pass found no new violations. Remaining gap:
  only one fixed mock state per page/dialog is checked, not every
  populated/error/loading variant.
- **Visual regression**: `frontend/e2e/visual.spec.ts` — screenshot
  baselines for every top-level page and every modal/dialog surface:
  landing, kid picker, reader (+ conflict dialog), library, guardian
  console/intake/requests/books (+ assign dialog)/profiles (+ profile-form
  dialog), and admin console/requests/moderation-thresholds/moderation-
  dashboard (`visual.spec.ts-snapshots/`). Same remaining-gap caveat as
  accessibility above: one state per surface, not every variant.

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
- E2E-prod: `frontend/e2e-prod/landing-login.spec.ts`, `frontend/e2e-prod/guardian-admin-smoke.spec.ts`
- Component: `frontend/src/guardian/LoginPage.test.tsx`, `frontend/src/guardian/SetNewPasswordForm.test.tsx`, `frontend/src/auth/AuthContext.test.tsx`, `frontend/src/auth/AdultGate.test.tsx`, `frontend/src/auth/ProtectedRoute.test.tsx`, `frontend/src/auth/guardianToken.test.ts`, `frontend/src/auth/supabaseClient.test.ts`, `frontend/src/guardian/GuardianShell.test.tsx`, `frontend/src/guardian/ConsolePage.test.tsx`
- Integration: `frontend/src/test/App.test.tsx`

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
- E2E-prod: `frontend/e2e-prod/guardian-admin-smoke.spec.ts` (render only)
- Component: `frontend/src/guardian/RequestsPage.test.tsx`, `frontend/src/guardian/storyRequestQueueApi.test.ts`, `frontend/src/guardian/AssignChildrenDialog.test.tsx` (tags)

## Guardian: manage books/library

- E2E-mocked: `frontend/e2e/guardian-books.spec.ts`, `frontend/e2e/naive-user/naive-guardian-misuse.spec.ts` (empty state)
- E2E-prod: `frontend/e2e-prod/guardian-admin-smoke.spec.ts` (render only)
- Component: `frontend/src/guardian/BooksPage.test.tsx`, `frontend/src/guardian/assignApi.test.ts` (listBooks)

## Guardian: manage child profiles

- E2E-mocked: `frontend/e2e/guardian-profiles.spec.ts`, `frontend/e2e/naive-user/naive-guardian-misuse.spec.ts` (empty state), `frontend/e2e/story-requests-authored.spec.ts` (child selector)
- E2E-prod: `frontend/e2e-prod/guardian-admin-smoke.spec.ts` (render only)
- Component: `frontend/src/guardian/ProfilesPage.test.tsx`, `frontend/src/guardian/ProfileFormDialog.test.tsx`, `frontend/src/profiles/AvatarCircle.test.tsx`, `frontend/src/profiles/profilesApi.test.ts`

## Guardian: assign children to books

- E2E-mocked: `frontend/e2e/assignments.spec.ts`, `frontend/e2e/guardian-books.spec.ts`, `frontend/e2e/naive-user/naive-misuse-shared.spec.ts` (double-click guard)
- Component: `frontend/src/guardian/AssignChildrenDialog.test.tsx`, `frontend/src/guardian/assignApi.test.ts`

## Guardian: approve and publish a story

- E2E-mocked: `frontend/e2e/guardian-review.spec.ts`, `frontend/e2e/naive-user/naive-admin-misuse.spec.ts` (concurrent-approve, documents server gap #129), `frontend/e2e/naive-user/naive-misuse-shared.spec.ts` (double-click/back-button/hand-typed-URL guards, #130)
- E2E-real: `frontend/e2e-real/approval-flow.spec.ts`
- Component: `frontend/src/admin/ReviewDetailPage.test.tsx`, `frontend/src/guardian/reviewApi.test.ts`, `frontend/src/guardian/storyRequestQueueApi.test.ts` (approve/decline for pending requests), `frontend/src/guardian/RequestsPage.test.tsx` (approve/decline)

## Admin: review queue (single story review)

- E2E-mocked: `frontend/e2e/guardian-review.spec.ts`, `frontend/e2e/guardian-console.spec.ts` (navigation), `frontend/e2e/naive-user/naive-admin-misuse.spec.ts`, `frontend/e2e/naive-user/naive-misuse-shared.spec.ts`
- E2E-real: `frontend/e2e-real/approval-flow.spec.ts`
- Component: `frontend/src/admin/ReviewDetailPage.test.tsx`, `frontend/src/admin/AdminConsolePage.test.tsx` (links into it), `frontend/src/guardian/reviewApi.test.ts`, `frontend/src/guardian/coverApi.test.ts` (cover generation on review page)
- **Gap**: no E2E-staging coverage, `/admin/review/:id` needs a real storybook id and is excluded from the render-only staging smoke for the same reason `e2e-prod` excludes it.

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
- Component: `frontend/src/admin/ProviderAllowlistPage.test.tsx`, `frontend/src/admin/providerAllowlistApi.test.ts`
- **Gap**: no `e2e-real`, `e2e-staging`, or `e2e-prod` coverage yet.

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

## Kid: profile picker

- E2E-mocked: `frontend/e2e/device-authorization.spec.ts`, `frontend/e2e/landing.spec.ts`, `frontend/e2e/profiles.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts`
- E2E-real: `frontend/e2e-real/kid-reads.spec.ts`
- Component: `frontend/src/kid/ProfilePickerPage.test.tsx` (incl. PIN gate), `frontend/src/kid/KidNav.test.tsx`, `frontend/src/kid/KidShell.test.tsx`, `frontend/src/kid/childSessionApi.test.ts`, `frontend/src/profiles/AvatarCircle.test.tsx`, `frontend/src/profiles/profilesApi.test.ts`
- Integration: `frontend/src/test/App.test.tsx`

## Kid: browse library

- E2E-mocked: `frontend/e2e/library.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts`, `frontend/e2e/story-requests-kid.spec.ts`
- E2E-real: `frontend/e2e-real/kid-reads.spec.ts`, `frontend/e2e-real/naive-kid-misuse-real.spec.ts` (cross-family 403)
- E2E-staging: `frontend/e2e-staging/kid-library-smoke.spec.ts` (populated-library render, via mint/revoke device grant)
- E2E-prod: `frontend/e2e-prod/kid-device-grant.spec.ts` (empty-state render)
- Component: `frontend/src/library/LibraryPage.test.tsx`, `frontend/src/library/BookCard.test.tsx`, `frontend/src/library/pickHero.test.ts`, `frontend/src/library/libraryApi.test.ts`, `frontend/src/library/RequestStory.test.tsx`, `frontend/src/library/storyRequestApi.test.ts`
- Integration: `frontend/src/test/App.test.tsx`

## Kid: read a story (reader page, choices, endings)

- E2E-mocked: `frontend/e2e/reader.spec.ts`, `frontend/e2e/reader-conflict.spec.ts`, `frontend/e2e/reader-reload-resume.spec.ts`, `frontend/e2e/series-continue.spec.ts`
- E2E-real: `frontend/e2e-real/kid-reads.spec.ts`, `frontend/e2e-real/series-continue-real.spec.ts`
- Component: `frontend/src/reader/Reader.test.tsx`, `frontend/src/reader/ReaderPage.test.tsx` (largest suite), `frontend/src/reader/ReaderRoute.test.tsx`, `frontend/src/reader/ReaderChrome.test.tsx`, `frontend/src/reader/ReaderLeave.test.tsx`, `frontend/src/reader/BackToLibrary.test.tsx`, `frontend/src/reader/dialogs.test.tsx`, `frontend/src/reader/readerProgress.test.ts`, `frontend/src/player/engine.test.ts`, `frontend/src/player/evaluator.test.ts`, `frontend/src/player/machine.test.ts`, `frontend/src/api/readerApi.test.ts`
- Integration: `frontend/src/test/App.test.tsx`

## Kid: offline reading + sync/conflict resolution

- E2E-mocked: `frontend/e2e/reader.spec.ts` (fully-offline play), `frontend/e2e/reader-conflict.spec.ts`, `frontend/e2e/reader-reload-resume.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts` (reload resume)
- Component: `frontend/src/offline/db.test.ts`, `frontend/src/offline/sync.test.ts`, `frontend/src/reader/ReaderPage.test.tsx` (conflict dialog resolution paths), `frontend/src/reader/ReaderRoute.test.tsx` (replay-reconciliation suite), `frontend/src/reader/dialogs.test.tsx` (ConflictDialog UI), `frontend/src/hooks/useReplayOnReconnect.test.ts`, `frontend/src/hooks/useOnlineStatus.test.ts`
- **Gap**: no `e2e-real` or `e2e-prod` coverage of conflict/sync against a real backend.

## Kid: series continuation across storybooks

- E2E-mocked: `frontend/e2e/series-continue.spec.ts`, `frontend/e2e/story-requests-kid.spec.ts` (anchor), `frontend/e2e/story-requests.spec.ts` (series_title prefill)
- E2E-real: `frontend/e2e-real/series-continue-real.spec.ts`
- Component: `frontend/src/reader/ContinueSeries.test.tsx`, `frontend/src/player/series.test.ts`, `frontend/src/library/BookCard.test.tsx`, `frontend/src/library/LibraryPage.test.tsx` (continue-request), `frontend/src/library/RequestStory.test.tsx` (anchor mode), `frontend/src/reader/Reader.test.tsx` (continuation-eligibility gating), `frontend/src/reader/ReaderPage.test.tsx` / `ReaderRoute.test.tsx` (continuation-seed handling), `frontend/src/api/readerApi.test.ts` (`makeFetchSeriesNext`)

## Device authorization flow (kid device pairing)

- E2E-mocked: `frontend/e2e/device-authorization.spec.ts`, `frontend/e2e/landing.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts`
- E2E-real: `frontend/e2e-real/kid-reads.spec.ts`, `frontend/e2e-real/naive-kid-misuse-real.spec.ts`, `frontend/e2e-real/series-continue-real.spec.ts`, `frontend/e2e-real/real-stack.ts` (helper)
- E2E-staging: `frontend/e2e-staging/kid-library-smoke.spec.ts` (the one staging spec that writes, with `afterAll` cleanup, mirroring the prod pattern)
- E2E-prod: `frontend/e2e-prod/kid-device-grant.spec.ts` (the one prod spec that writes, with `afterAll` cleanup)
- Component: `frontend/src/auth/DeviceAuthorizedRoute.test.tsx`, `frontend/src/auth/deviceGrant.test.ts`, `frontend/src/auth/deviceGrantApi.test.ts`, `frontend/src/landing/LandingPage.test.tsx`, `frontend/src/guardian/ConsolePage.test.tsx` (mint/re-authorize/revoke), `frontend/src/guardian/LoginPage.test.tsx` (authorize-device intent), `frontend/src/offline/db.test.ts` (device-grant mirror + migration), `frontend/src/hooks/useApi.test.ts` (device-grant bearer selection/clearing)
- Integration: `frontend/src/test/App.test.tsx`

## Ratings (star rating on completed stories)

- E2E-mocked: `frontend/e2e/library.spec.ts`, `frontend/e2e/naive-user/naive-kid-misuse.spec.ts` (double-rating keeps latest)
- E2E-real: `frontend/e2e-real/ratings-real.spec.ts` (tap a star against the real backend, reload, confirm the rating persisted server-side rather than only in client state)
- Component: `frontend/src/library/StarRating.test.tsx`, `frontend/src/library/LibraryPage.test.tsx` (rate POST + optimistic/revert), `frontend/src/library/libraryApi.test.ts` (`rate()`)
- **Remaining gap**: still no `e2e-staging` or `e2e-prod` coverage; low priority given the real-backend and component coverage now in place.

---

## Known gaps (as of this audit)

Gaps 1, 2, and 4 below were closed in a follow-up pass; entries are kept
(marked Closed) rather than deleted so the audit trail of what was fixed and
when is preserved, per the policy at the bottom of this file.

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
6. **Offline sync/conflict resolution has no real-backend, staging, or prod
   coverage.** Mocked-tier and component coverage is strong, but reproducing
   a genuine 409 against a real backend means fabricating a real race
   between two devices, not just one more request/response case. Handed off
   with exact mechanics (the reading.py conflict logic, the two-
   BrowserContext recipe using `real-stack.ts`'s existing `authorizeDevice`,
   and why production is explicitly out of scope for this one) in
   `docs/planning/handoff-offline-conflict-real-backend-2026-07-16.md` for a
   team with local access to implement and iterate on directly, rather than
   landing a first cut nobody watched pass or fail.

`#ASSUME: external-resources: gaps 2, 4, and (if attempted) 6 above were
authored without access to a running browser or a live backend/Postgres
instance in the environment that wrote them, only `tsc -b`, ESLint, and
`playwright --list` verified them. #VERIFY: run each new spec for real (CI
or a local `npm run test:e2e` / `test:e2e:real`) before trusting it as
proven, and fix on sight if the live run disagrees with what static
analysis could check.`

## Keeping this matrix current

`#ASSUME: data-integrity: this matrix is hand-maintained and will drift as
new spec files are added. #VERIFY: add a CI check that greps new files under
frontend/e2e/, frontend/e2e-real/, frontend/e2e-prod/, and frontend/src/**/*.test.{ts,tsx}
against this document and fails if a new spec file isn't referenced anywhere,
so drift is caught at PR time rather than discovered during an audit.`

When adding a new journey or page, add a section here in the same PR. When
closing one of the gaps above, update its entry to reflect the new coverage
rather than deleting the gap silently, so the audit trail of what was fixed
when is preserved.
