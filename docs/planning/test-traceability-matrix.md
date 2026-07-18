---
title: "Test Traceability Matrix: Register Capabilities x E2E Environments"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Map every capability register ID to its end-to-end test coverage per environment
  (local mocked, local real backend, staging, production), define the golden journeys that
  must hold the full ladder, and specify the alerting wiring so a broken workflow surfaces
  without anyone checking the Actions tab."
tags:
  - planning
  - testing
  - scope
component: Strategy
source: "E2E inventory subagent + supervising review, 2026-07-16; complements PR #268's
  docs/testing/coverage-matrix.md (journey-by-page keyed) with a register-keyed view."
---

# Test Traceability Matrix (2026-07-16)

> **Status**: Active | Companion to [capability-register.md](./capability-register.md)
> (v1.5) and, once PR #268 merges, `docs/testing/coverage-matrix.md`.

## The bar (owner directive, 2026-07-16)

Every shipped workflow must have an E2E test in **local, staging, and production**, wired
so a failure alerts quickly. "Local" has two tiers here: mocked (runs on every PR) and
real-backend (full stack against seeded Postgres). The ladder for a capability is
therefore: mocked -> real -> staging -> prod, with scheduled runs and active alerting on
the last two.

## Current CI wiring (the alerting problem, stated plainly)

| Tier | Where it runs | Alerting today |
|------|---------------|----------------|
| e2e (mocked) | `ci.yml` frontend job, every PR/push/merge-group | ✅ red PR check blocks merge |
| e2e-real | Nowhere; deliberately local-only pre-PR | ❌ none |
| e2e-staging (PR #268) | Daily cron 13:00 UTC + manual, once merged and its three `staging` environment secrets are set | ❌ passive only: a red run in the Actions tab, trace artifact, no notification |
| e2e-prod | Nowhere; spec headers say manual trigger only | ❌ none, and no schedule exists |

**Consequence**: today, a production breakage in any workflow is discovered by a family
member hitting it, not by CI. Closing that is the point of the actions list below.

## Capability x environment matrix

Legend: ✅ covered; 🟡 partial/smoke; ❌ gap (capability shipped, tier missing);
PR268 = coverage arrives with PR #268; n/b = capability not built yet (no test possible;
row must fill when it ships); srv = enforced server-side, covered by backend unit and
integration suites rather than browser E2E.

| ID | Capability (short) | Mocked | Real | Staging | Prod |
|----|--------------------|--------|------|---------|------|
| K1 | Age-appropriate presentation | PR268 (a11y suite) | ✅ | ❌ | ❌ |
| K2 | Choices, hidden when locked | ✅ | ✅ | ❌ | ❌ |
| K3 | Consequential state, series carry | ✅ | ✅ | ❌ | ❌ |
| K4 | Resume anywhere | ✅ | ❌ | ❌ | ❌ |
| K5 | Replay + Go Back undo | ✅ (e2e/reader-go-back.spec.ts; unit: engine.test.ts) | ❌ | ❌ | ❌ |
| K6 | Endings tracker | 🟡 (completion recorded; tracker UI n/b) | ❌ | ❌ | ❌ |
| K7 | Read-aloud | n/b | n/b | n/b | n/b |
| K8 | Covers on the shelf | ✅ (e2e/library.spec.ts + BookCard.test.tsx; A16 button pin: admin-review-cover.spec.ts) | ❌ | ❌ | ❌ |
| K9 | Library shelf | ✅ | ✅ | ✅ (populated-library smoke) | 🟡 (library opens) |
| K10/S1 | Offline reading | ✅ | ❌ | ❌ | ❌ |
| K11 | Kid story request | ✅ | ❌ | ❌ | ❌ |
| K12 | Kid-friendly states | ✅ | ❌ | ❌ | ❌ |
| K13 | Band content guarantee | srv | srv | ❌ | ❌ |
| K14 | Safe room | 🟡 (avatar presets, no-upload) | ❌ | ❌ | ❌ |
| K15 | Feedback flag | n/b | n/b | n/b | n/b |
| K16 | Picker, PIN, sibling isolation | ✅ | ✅ (IDOR) | ✅ | ✅ |
| K17 | Recommendations | n/b | n/b | n/b | n/b |
| K18 | Star ratings | ✅ | PR268 | ❌ | ❌ |
| K19 | Request interpretation preview | n/b | n/b | n/b | n/b |
| G1 | Profiles that shape experience | ✅ | ❌ | ❌ | ❌ |
| G2/G3 | Content controls; per-child permissions | n/b (UI) | n/b | n/b | n/b |
| G4 | Guardian-initiated stories | ✅ | ✅ | ❌ | ❌ |
| G5 | Review skim aids | 🟡 | ❌ | ❌ | ❌ |
| G6 | Edit/reject | n/b | n/b | n/b | n/b |
| G7 | Cost gate (consent step) | ✅ (incl. double-approve race) | ❌ | ❌ | ❌ |
| G8-G13 | Kill switch UI, visibility, notifications, trust, export, balance | n/b | n/b | n/b | n/b |
| G14 | Adult auth incl. dual-role | ✅ | ✅ | ✅ | ✅ |
| G15 | Device grants | ✅ | ❌ | ✅ (mint/revoke) | ✅ (mint/revoke) |
| G16 | Catalog browse + assign | ✅ | ❌ | ❌ | ❌ |
| G17 | Connection consent | n/b | n/b | n/b | n/b |
| A1 | Review queue + dashboard | ✅ | ✅ | 🟡 (render smoke) | 🟡 (render smoke) |
| A3 | Threshold levers | PR268 | PR268 | ❌ | ❌ |
| A6 | Approve-and-publish | ✅ | ✅ | ❌ | ❌ |
| A8 | Provider allowlist + authoring plan | PR268 | PR268 | ❌ | ❌ |
| A10 | Admin-initiated requests | ✅ | 🟡 | ❌ | ❌ |
| A12/A15 | User mgmt; connections console | PR267 (specs ride the PR) | ❌ | ❌ | ❌ |
| A16 | Cover generation | ❌ | ❌ | ❌ | ❌ |
| S2 | Conflict resolution | ✅ | 🟡 (spec written: `offline-conflict-real.spec.ts`; runs nightly via `e2e-real-nightly.yml`, not yet observed passing in CI) | ❌ | ❌ |
| S8 | Request -> shelf pipeline | ✅ (segmented) | 🟡 (seeded, no live generate) | ❌ | ❌ |
| S10 | PII/IDOR boundaries | ✅ | ✅ | ❌ | ❌ |
| S11 | Social/device boundary | ✅ | ❌ | 🟡 | 🟡 |

Rows n/b are the register's own delivery gaps; they enter this matrix the day the
capability ships (maintenance rule below).

> **2026-07-17 addendum (M4b-d wave)**: formerly-n/b capabilities shipped with mocked-tier
> coverage in the same commits: K6 (library/reader specs), K7 (kid-read-aloud.spec), K15
> (reader-flag.spec), K17 (library.spec chips), G2/G3 (guardian-profiles + component
> suites), G5 (component suites), G6 (unit + component; no e2e yet), G9/G10
> (guardian-reading.spec, guardian-notifications.spec), G13 (story-requests.spec), G17
> (unit + component; no e2e yet). Real/staging/prod tiers for these follow the Phase 5
> ladder actions; rows to be normalized into the table on the next matrix revision.

## Golden journeys (the full-ladder set)

Rather than pushing all ~40 shipped capabilities to all four tiers, the ladder bar
applies to five golden journeys that collectively cross every core value loop; everything
else needs mocked + one real-environment tier minimum.

| # | Journey | Register IDs swept | Ladder today |
|---|---------|--------------------|--------------|
| GJ1 | Kid picks profile -> opens populated library -> reads to an ending (incl. one state-gated choice) -> progress survives reload | K16, K9, K2, K3, K4, K6, S1 | mocked ✅ real ✅ staging 🟡 prod 🟡 (both stop at "library opens") |
| GJ2 | Kid requests a story -> guardian approves -> admin builds authoring plan -> pipeline runs -> admin approves -> book reaches the kid's shelf | K11, G7, A10, A8, A6, S8, K9 | mocked ✅ (segments) real 🟡 staging ❌ prod ❌ |
| GJ3 | Guardian assigns a catalog book -> kid reads it -> kid rates it | G16, K9, K18 | mocked ✅ real 🟡 staging ❌ prod ❌ |
| GJ4 | Guardian authorizes a device -> kid reads offline -> reconnect syncs -> guardian revokes device | G15, K16, S1, S2, S11 | mocked ✅ real ❌ staging 🟡 prod 🟡 (no offline/sync leg anywhere real) |
| GJ5 | Admin moderation loop: flagged story -> review detail -> send back or approve -> thresholds edited -> dashboard reflects it | A1, A6, A3 | mocked ✅/PR268 real ✅/PR268 staging ❌ prod ❌ |

## Actions to reach the bar

1. **Merge PR #268 and set the three `staging` environment secrets**
   (`E2E_STAGING_BASE_URL`, `E2E_STAGING_GUARDIAN_PASSWORD`, `E2E_STAGING_ADMIN_PASSWORD`);
   without them the staging tier is dead code.
2. **Add active alerting to every scheduled run**: a shared on-failure step in
   `e2e-staging.yml` (and the new prod workflow below) that opens or appends to a pinned
   GitHub issue labeled `e2e-alert` with the run link. Repo watchers then get email/push
   from GitHub natively. This is the cheapest "quickly alerted" mechanism; a messaging
   webhook can layer on later.
3. **Done** (`.github/workflows/e2e-prod.yml`): daily cron `30 13 * * *` (offset from
   staging) + manual dispatch, running the existing `e2e-prod` specs against the live URL
   with a dedicated test family, plus the pinned-issue `e2e-alert` step. The device-grant
   spec already demonstrates safe prod writes (mint then revoke); prod additions stay
   read-mostly.
4. **Extend staging beyond smoke to GJ2, GJ3, GJ5**: staging is the only environment
   where the full generate-moderate-approve pipeline can run repeatedly without touching
   family prod data; seed it with a standing test family, admin, and a mock-provider or
   cheap-model configuration. This is the single highest-value gap: the app's core value
   loop (GJ2) currently has no scheduled verification anywhere.
5. **Promote GJ1 and GJ4 in prod from smoke to journey**: extend the existing prod specs
   so the kid actually opens a book and reaches a page (GJ1), and add the offline
   toggle + resync leg to GJ4 where Playwright's offline emulation permits.
6. **Done** (`.github/workflows/e2e-real-nightly.yml`): nightly cron `30 9 * * *`
   (Postgres + Redis service containers, real Supabase migrations, `seed_dev_data.py`,
   backgrounded uvicorn) plus manual dispatch, kept out of the PR path. Also absorbs the
   S2 conflict-race handoff: `frontend/e2e-real/offline-conflict-real.spec.ts` now runs in
   this job (see the S2 row above).
7. **Close the two shipped-but-untested rows**: K5 (assert Go Back returns to the prior
   node without state corruption; it was just ratified, it deserves a pin) and K8/A16
   (cover renders when present, letter-tile fallback when absent; admin generate button
   enqueues).

## Maintenance rules

1. A capability leaving n/b (shipping) must add its row here in the same PR, with at
   least mocked-tier coverage; golden-journey membership is decided at the same moment.
2. A new golden journey requires owner sign-off; the five above are the 2026-07-16 set.
3. When PR #268's `docs/testing/coverage-matrix.md` merges, that file stays the
   page/journey inventory and this file stays the register-keyed view; changes to either
   should cross-check the other until a CI drift check exists.

## Related documents

- [Capability register](./capability-register.md)
- [Traceability review 2026-07-16](./traceability-review-2026-07-16.md)
- PR #268: `docs/testing/README.md`, `docs/testing/coverage-matrix.md`,
  `.github/workflows/e2e-staging.yml`
