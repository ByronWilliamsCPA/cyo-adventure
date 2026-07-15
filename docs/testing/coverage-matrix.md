# Frontend Test Coverage Matrix

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
- Component: incidental only, no dedicated module test. `frontend/src/guardian/RequestsPage.test.tsx` has one test for the anchored-row continuation note; `screened`/`flagged_count` fields ride along in `ReviewDetailPage.test.tsx`, `AdminConsolePage.test.tsx`, `AssignChildrenDialog.test.tsx`, `FlagBadge.test.tsx`, `BooksPage.test.tsx`
- **Gap**: no standalone unit test for screening/anchoring logic itself, only E2E and incidental fixture assertions. See Gaps section.

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

- E2E-mocked: **NONE FOUND**
- E2E-staging: `frontend/e2e-staging/guardian-admin-smoke.spec.ts` (render smoke only)
- E2E-prod: `frontend/e2e-prod/guardian-admin-smoke.spec.ts` (render smoke only)
- Component: `frontend/src/admin/ModerationDashboardPage.test.tsx`, `frontend/src/admin/ModerationThresholdsPage.test.tsx`, `frontend/src/admin/AdminShell.test.tsx` (nav link only)
- **Gap**: solid component coverage and now a staging render smoke, but no dedicated mocked or real-backend E2E spec exercises the actual thresholds-editing or dashboard-filtering workflow end-to-end. See Gaps section.

## Admin: provider allowlist management

- **NONE FOUND** at any layer (E2E-mocked, E2E-real, E2E-prod, or Vitest). No `ProviderAllowlist` page exists under `frontend/src/admin/`; the only "allowlist" references in `frontend/src` are inside the generated API client (`frontend/src/client/types.gen.ts`, `sdk.gen.ts`, `index.ts`) and `frontend/src/hooks/useApi.ts`. See Gaps section, this may be a missing UI rather than a missing test.

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
- Component: `frontend/src/library/StarRating.test.tsx`, `frontend/src/library/LibraryPage.test.tsx` (rate POST + optimistic/revert), `frontend/src/library/libraryApi.test.ts` (`rate()`)
- **Gap**: no `e2e-real`, `e2e-staging`, or `e2e-prod` coverage.

---

## Known gaps (as of this audit)

1. **Screening/anchoring**: no standalone unit-tested module; coverage is
   incidental (data-fixture assertions inside page tests) plus a few E2E
   scenarios. Priority: Medium, this is core intake logic but currently
   protected transitively by intake/request E2E specs.
2. **Moderation dashboard/thresholds**: strong component coverage, but no
   dedicated mocked-tier (`frontend/e2e/`) or real-backend (`frontend/e2e-real/`)
   spec that actually exercises editing thresholds or filtering the
   dashboard, only render-only smoke on staging and prod. Priority: High,
   this gates what content reaches production and has no workflow-level
   regression coverage.
3. **Provider allowlist management**: no coverage found at any layer; no
   admin UI page appears to exist in the frontend for this at all. Priority:
   needs confirmation, first determine with the team whether this is
   intentionally backend/CLI-only or a missing page before treating it as a
   test gap.
4. **Ratings**: no `e2e-real`/`e2e-staging`/`e2e-prod` coverage, mocked-tier
   and component coverage only. Priority: Low, low-risk UI action, component
   coverage is adequate for now.
5. **The new E2E-staging tier is smoke-only, not full-journey.** It covers
   only render checks (`guardian-admin-smoke.spec.ts`) and one populated-
   library check via device grant (`kid-library-smoke.spec.ts`); it does not
   exercise intake, screening, approval, assignments, or moderation
   workflows end to end the way `e2e-real` does locally. There is also still
   no `dev`-tier environment (see `docs/testing/README.md`); that requires a
   frontend deploy pipeline this repo does not own.
6. **Offline sync/conflict resolution has no real-backend, staging, or prod
   coverage.** Mocked-tier and component coverage is strong, but the
   conflict-resolution path has never been exercised against a real
   database.

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
