---
title: "Action-Level Coverage Robustness Verdict"
schema_type: common
status: published
owner: core-maintainer
purpose: "Verifies every user-facing action/flow in the current web interface has
  robust test coverage to the extent each environment allows; grades each area by
  tier and lists the true holes and per-environment gaps. Source: session 2026-07-22,
  branch test/comprehensive-e2e-audit, two code-grounded enumeration passes."
tags:
  - testing
  - coverage
---

Companion to [`coverage-matrix.md`](coverage-matrix.md). Where the matrix maps
*journeys* to specs, this document answers the sharper question: does **every
distinct action** the current web interface exposes have robust testing, to the
extent each environment can physically support? It is the join of two
independent, code-grounded enumeration passes (one over the frontend action
surface, one over the actual spec bodies at all five tiers), so it verifies
completeness against code rather than trusting the hand-maintained matrix.

## Method

- **Surface pass:** enumerated the live action surface from `router.tsx`,
  `routeElements.tsx`, `auth/*`, `offline/*`, `player/series.ts`, the `*Api.ts`
  modules, and every page component. Result: **~203 distinct actions** across
  landing / kid / guardian / admin / cross-role, plus **8 cross-cutting flows**
  (offline sync+conflict, offline-copy revocation, device authorization, series
  continuation, PIN gate, adult step-up gate, session-expiry/redirect, and the
  request to authoring to generation to review to publish chain).
- **Coverage pass:** read the actual spec bodies for all 34 mocked, 9 real, 2
  staging, and 3 prod E2E specs, and indexed the 119 component/unit test files,
  then diffed against `coverage-matrix.md`.
- Numbers are grounded in code as of the branch head; component-tier assertion
  *depth* was filename/skim-verified, not body-verified, so component-only
  grades below mean "a test file exists and plausibly covers this," not
  "every branch is asserted."

## Headline verdict

The **content pipeline core is robustly tested** at every tier it can be:
guardian/admin auth, story request intake and approval, admin review and
publish, authoring plan, kid read-to-ending (online and offline), series
continuation, ratings, device authorization, and (now, after this session's
fix) offline multi-device conflict all have component + mocked + real-backend
coverage. Device authorization is the single best-covered flow, exercised at
all five tiers.

Three things are true at once, and they are the answer to "is everything
robustly tested":

1. **No user-facing action is completely untested at the *content* level.**
   Every route renders under `a11y.spec.ts` and `visual.spec.ts`, and every
   major `src/` module has a component test.
2. **~10 real, shipped feature areas are component-tier-only, with no E2E at
   any tier** (listed below). They are not holes in the "nothing tests this"
   sense, but they lack any browser-level integration proof, which is where the
   defects a real user hits (routing, guards, multi-call sequences) actually
   surface.
3. **The two environments closest to real users (staging, prod) are
   smoke-only.** They verify pages render plus one reversible device-grant
   round trip, and nothing of the content pipeline. This is the realism-vs-depth
   inversion and it is the main structural gap.

## Robustness by area x tier

Legend: C = component/unit, M = E2E-mocked, R = E2E-real, S = E2E-staging,
P = E2E-prod. ✓ = covered, · = not covered, ~ = render/smoke only.

| Area (persona) | C | M | R | S | P | Verdict |
| --- | :-: | :-: | :-: | :-: | :-: | --- |
| Guardian/admin password auth | ✓ | ✓ | ✓ | ✓ | ~ | **Robust** |
| Device authorization (ADR-014) | ✓ | ✓ | ✓ | ✓ | ✓ | **Robust** (best-covered) |
| Kid read to ending / choices / offline play | ✓ | ✓ | ✓ | · | · | **Robust-local** |
| Offline multi-device sync + conflict | ✓ | ✓ | ✓ | · | · | **Robust-local** (fixed 2026-07-22) |
| Series continuation | ✓ | ✓ | ✓ | · | · | **Robust-local** |
| Ratings | ✓ | ✓ | ✓ | · | · | **Robust-local** |
| Story request submit (kid/guardian/admin) | ✓ | ✓ | ✓ | · | · | **Robust-local** |
| Approve and publish | ✓ | ✓ | ✓ | · | · | **Robust-local** |
| Admin review queue (single story) | ✓ | ✓ | ✓ | ~ | ~ | **Robust-local** |
| Authoring plan (method/model) | ✓ | ✓ | ✓ | · | · | **Robust-local** |
| Moderation thresholds/dashboard | ✓ | ✓ | ✓ | ~ | ~ | **Robust-local** (1 corpus gap) |
| Cross-family authorization (403/401) | ✓ | ✓ | ✓ | · | · | **Robust-local** |
| Guardian books / assign children | ✓ | ✓ | ✓ | · | · | Solid-local |
| Guardian profile CRUD | ✓ | ✓ | · | · | · | Solid-local (no real) |
| Intake concept to generate | ✓ | ✓ | · | · | · | Solid-local (LLM, real N/A) |
| Provider allowlist CRUD | ✓ | ✓ | · | · | · | Solid-local (no real) |
| Notifications (G10) | ✓ | ✓ | · | · | · | Solid-local (orphan spec) |
| Reading history (G9) | ✓ | ✓ | · | · | · | Solid-local (orphan spec) |
| Read-aloud (K7) | ✓ | ✓ | · | · | · | Solid-local (orphan spec) |
| Flag a passage (K15) | ✓ | ✓ | · | · | · | Solid-local (orphan spec) |
| Go-back / undo (K5) | ✓ | ✓ | · | · | · | Solid-local (orphan spec) |
| Cover generation (A16) | ✓ | ✓ | · | · | · | Solid-local (orphan spec) |
| Admin user/profile/family mgmt (WS-J) | ✓ | ✓ | · | · | · | Solid-local (orphan spec) |
| **Guardian family connections (Allow/Revoke consent)** | ✓ | · | · | · | · | **Component-only** |
| **Admin audit log (filter/page)** | ✓ | · | · | · | · | **Component-only** |
| **Admin library lifecycle filter** | ✓ | · | · | · | · | **Component-only** |
| **Review version-compare panel** | ✓ | · | · | · | · | **Component-only** |
| **Passage-edit save (node PATCH)** | ✓ | · | · | · | · | **Component-only** |
| **Password reset / set-new / cross-tab recovery** | ✓ | · | · | · | · | **Component-only** |
| **Consent gate / awaiting-approval interstitial** | ✓ | · | · | ~ | ~* | **Component-only** (*prod manually verified this session) |
| **Google / Apple OAuth sign-in** | ✓ | · | · | · | · | **Component-only** (no automated E2E) |
| **Offline-copy revocation reconcile** | ✓ | · | · | · | · | **Component-only** |

## Confirmed component-only thin spots (the actionable gaps)

These are real, shipped surfaces with a component test but **no browser-level
proof at any E2E tier**. Greps against all four E2E directories confirmed the
absence (keyword hits were false matches: "reset" of state, "connection-ring"
recommendation copy, "passage" prose in reader specs). Ranked by user exposure:

1. **Consent gate / awaiting-approval** (COPPA/GDPR, PR #311). Every real
   guardian's first authenticated screen. Component-tested and manually
   prod-verified this session, but has no automated E2E asserting the gate is
   passable and unblocks action routes. Highest leverage: a mocked spec that
   signs in a `needs-consent` principal, fills legal name + checkbox, submits,
   and asserts `/guardian/intake` stops redirecting.
2. **Guardian family connections** (Allow/Revoke cross-family consent, the
   ADR-016 three-ring boundary). Consent grant/revoke is a privacy-load-bearing
   write with only component coverage.
3. **Passage-edit save** on the review page. Editors mutate story content via
   `PATCH .../nodes/{id}`; the save path has component coverage but no E2E,
   despite the surrounding review page (approve/send-back/cover) being
   E2E-covered.
4. **Password reset / set-new-password / cross-tab `BroadcastChannel`
   recovery.** Account-recovery is a classic support-ticket generator and the
   cross-tab handoff is invisible to a single-tab suite.
5. **Admin audit log, admin library lifecycle filter, review version-compare.**
   Lower user exposure (admin-only, read-heavy) but each is a routed page whose
   filter/paging/compare wiring is only unit-tested.
6. **OAuth sign-in (Google live in staging, Apple flag-gated).** Not
   mock-testable, and not automated against staging even though Google login is
   live there. Realistically a manual or staging-scripted check.
7. **Offline-copy revocation reconcile.** Purges cached stories no longer on the
   shelf; component-only, and has a known latency gap (a book unassigned
   mid-read is not caught until the next library fetch).

## Per-environment ceiling (what "to the extent possible" means)

| Environment | What it *can* robustly test | What it structurally *cannot* today |
| --- | --- | --- |
| **Local mocked** (34 specs) | Every route, every guard, most confirm-gated/double-submit patterns, all error/empty states via route interception | Real authorization, real strict-schema rejection (the exact class the offline 422 fell into), real DB persistence |
| **Local real** (9 specs) | The full content pipeline against real Postgres + Supabase + real 403/401/409 | Broad breadth (cost); currently omits profile CRUD, allowlist, notifications, reading-history, read-aloud, flag, go-back, cover-gen, user-mgmt |
| **Staging** (2 specs, smoke) | That deployed pages render and one device-grant round-trips against shared Supabase | Any content-pipeline regression; ephemeral seed passwords make deeper specs non-reproducible locally |
| **Prod** (3 specs, smoke) | Public surfaces render; one reversible device-grant mint/revoke; no data created by design | Approval, authoring, moderation, rating, read-to-ending: deliberately none, to avoid live writes |
| **Dev** | Nothing automated | No Playwright tier exists; manual browser smoke only (no frontend deploy pipeline this repo owns) |

`#ASSUME: data-integrity: coverage depth is inversely correlated with realism
(mocked > real > staging/prod). #VERIFY: the two tiers closest to real users
give almost no content-pipeline regression signal; the staging stale-image bug
(handoff 2026-07-21) is exactly the class of defect only a deeper staging tier
would have caught before a user did.`

## Suspected micro-holes needing spot verification

Surfaced by the surface pass as easy-to-miss branches; whether the existing
component test asserts each was NOT confirmed in this pass (filename/skim only).
Verify before assuming covered:

- **Modified-click / new-tab** on the profile-picker tile (Cmd/Ctrl/Shift/Alt
  falls through to native `<Link>`, skipping the mint-then-navigate flow).
- **Read-aloud "broken" latch** (first `speak()` throw permanently hides the
  toggle for the session).
- **Cover-generation timeout** (30x2s poll exhausts without leaving
  `'generating'`), distinct from busy and failed.
- **Endings-tracker under-report race** (`EndingsProgress` can race the
  fire-and-forget completion POST; must never over-count).
- **Unknown-category threshold override** routes through an *extra* confirm
  dialog vs a known category; **noise-floor 0.3 boundary** toggles an extra
  warning paragraph.
- **Unreachable-passage edit** shares wiring with reachable-passage edit; easy
  to test one and skip the other.
- **`ProfileFormDialog` envelope "touched" gating** is load-bearing: including
  untouched `request_auto_approve`/`monthly_request_envelope` 422s the whole
  PATCH today (`extra="forbid"`), same failure class as the offline bug.
- **`GET /v1/device-grants` (list)** has no confirmed call site; verify whether
  it is dead code before writing coverage for it.

## Matrix drift corrected in this pass

The independent coverage pass found `coverage-matrix.md` had drifted **by
omission, not inaccuracy** (all 116 file paths it cites exist; it under-claims,
never over-claims):

- **8 orphan specs** existed on disk but were unreferenced, all covering real
  register-numbered features: `admin-review-cover` (A16), `admin-user-management`
  (WS-J), `guardian-notifications` (G10), `guardian-reading` (G9),
  `kid-read-aloud` (K7), `reader-flag` (K15), `reader-go-back` (K5), and
  `offline-conflict-real`. Added to the matrix.
- **Known gap #6 was factually stale:** it claimed offline sync/conflict had no
  real-backend coverage, but `offline-conflict-real.spec.ts` closes exactly that
  gap (and now passes 4/4 after the 2026-07-22 `toPutPayload` fix). Corrected.

## Prioritized plan to raise robustness

1. **Close the consent-gate E2E hole** (mocked tier). Highest user exposure;
   every guardian passes it. One spec.
2. **Add the CI drift-guard the matrix asks for**: fail PR CI if a new
   `frontend/e2e*/**.spec.ts` or `src/**/*.test.tsx` is not referenced in
   `coverage-matrix.md`. This prevents the 8-orphan recurrence structurally.
3. **Backfill E2E for the component-only privacy/content writes**: family
   connections consent, passage-edit save, password recovery. Mocked tier first;
   promote the connections + passage-edit ones to real-backend since they are
   real mutations.
4. **Deepen the real-backend tier** toward the 10 Solid-local areas that are
   mocked-only (profile CRUD, allowlist, notifications, reading-history,
   read-aloud, flag, go-back, cover-gen, user-mgmt), prioritizing writes.
5. **Make staging more than smoke** once the ephemeral-seed-password problem is
   solved (record seed passwords in a secret manager at seed time). A single
   real approval-and-read journey on staging would have caught the stale-image
   bug.
6. **Verify the micro-holes** above and add targeted component assertions where
   missing.
7. **Spot-verify component assertion depth** for the areas graded Component-only,
   since this pass confirmed file existence, not branch coverage.

## Keeping this current

This verdict is a point-in-time snapshot (branch head, 2026-07-22). It goes
stale the same way the matrix does. Recommendation 2 (the CI drift-guard) is the
durable fix; until it lands, re-run the two enumeration passes before trusting
this document for release decisions.
