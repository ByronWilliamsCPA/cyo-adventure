---
purpose: What's needed to add real-backend/staging/prod E2E coverage for offline reading-state conflict resolution
component: testing infrastructure, frontend/e2e-real, backend reading-state API
source: Frontend testing infrastructure review, 2026-07-16
---

# Handoff: offline conflict resolution needs real-backend E2E coverage

Written 2026-07-16, for whoever picks this up next with local access to run
the real-backend E2E tier. This is coverage-matrix gap #6
(`docs/testing/coverage-matrix.md`): the offline sync/conflict-resolution
path (two devices racing a save, the app's `ConflictDialog`) has strong
mocked-tier and component coverage but has never been exercised against a
real backend, real Postgres, or real staging/production. This doc has the
exact mechanics worked out; what's missing is someone actually running it
against a live stack and iterating on the inevitable first-run surprises,
which this session couldn't do unattended with confidence.

## Why this wasn't just done in the same pass as the other real-backend additions

Two prior gaps (ratings, moderation) got real-backend specs directly because
each was a straightforward "do the same action, hit the real API, assert
the real result" case with an existing pattern to copy. This one is
different in kind: it requires deliberately **fabricating a race condition**
(two "devices" writing to the same reading-state row with a stale revision)
rather than just exercising a single request/response. That's a more
invasive test to get right blind, and this pass prioritized get it
correctly-scoped over rushing a possibly-flaky first cut. The mechanics
below should make the actual implementation quick for someone who can run
it and watch it fail/pass a few times.

## The conflict mechanism (verified from source, not guessed)

`PUT /api/v1/reading-state/{profile_id}/{storybook_id}`
(`src/cyo_adventure/api/reading.py`) takes a body including `version`,
`state_revision`, and `event_id`. The row is fetched `FOR UPDATE`, then:

1. If `body.event_id == row.last_event_id`: idempotent replay, 200, no
   revision bump.
2. Else if `body.version != row.version`: 409, `"version mismatch"`.
3. Else if `body.state_revision != row.state_revision`: 409,
   `"revision mismatch"`.
4. Otherwise: applies the write, `state_revision = body.state_revision + 1`.

The first save for a profile/story pair must carry `state_revision == 0`
(a later one is a 422, not a fresh conflict). The 409 body
(`ConflictView`) is `{detail, current_row: ReadingStateView, options:
["continue_from_this_device", "use_newer_progress"]}` — this is exactly
the shape `frontend/src/reader/ConflictDialog.tsx` and the mocked
`frontend/e2e/reader-conflict.spec.ts` already expect, so the frontend
side needs no changes, only a real trigger.

Existing backend pytest coverage already proves this mechanism works in
isolation (`tests/integration/test_reading_state.py`):
`test_reading_state_round_trip`, `test_stale_revision_returns_409`,
`test_version_mismatch_returns_409`. This handoff is about proving the
**frontend's** conflict-resolution flow (the dialog, `continue_from_this_device`
rebase-and-resave, `use_newer_progress` adopt-and-remount) against a real
409 from a real backend, not re-proving the backend logic pytest already
covers.

## How to fabricate a real conflict (the actual test recipe)

`frontend/e2e-real/real-stack.ts` already exports `authorizeDevice(context)`
and `revokeDevice(grant)`, used by every other real-backend kid-surface
spec to mint a real, family-scoped device grant into a Playwright
`BrowserContext`. Two devices means two contexts:

1. Open **two separate Playwright `BrowserContext`s** (not just two pages/tabs
   in one context, since the device-grant and reading-state need to look
   like genuinely separate clients), each authorized via `authorizeDevice`.
2. **Device A** navigates to the reader for a standalone seeded story (e.g.
   `s_tide_pools`, "The Tide Pool Mystery", per `scripts/seed_dev_data.py`)
   and makes a choice, so its first save lands at `state_revision == 0` and
   the resulting real PUT succeeds, creating the row server-side.
3. **Device B**, which loaded the reader at the same starting state before
   A's write landed, makes its own choice. Its PUT still carries
   `state_revision == 0` (the client-side revision it started with), so the
   server now rejects it with a real 409, `current_row` populated with A's
   actual persisted state.
4. Assert `ConflictDialog` renders on device B with A's real position, then
   drive both resolution paths (`continue_from_this_device` and
   `use_newer_progress`) exactly like the mocked spec does, but against real
   subsequent PUTs instead of mocked ones.

## What isn't seeded yet (a real gap to fill first)

Neither `scripts/seed_dev_data.py` nor `scripts/seed_staging.py` create any
`ReadingState` rows — confirmed, neither script imports the `ReadingState`
model at all. So there is no pre-existing reading-state row to race against;
the test itself has to create the first save (device A's write) before
device B's stale write can conflict. That's already accounted for in the
recipe above (step 2 creates the row; step 3 conflicts against it), so no
seed script change should be needed for the **local** real-backend tier.

## Staging and production tiers: bigger open question

The same recipe should work against staging (`frontend/e2e-staging/`) using
the seeded "Test Reader" profile and one of its two published stories, once
the `dev`/`staging` secrets from the other outstanding handoff
(`handoff-homelab-infra-dev-environment-2026-07-16.md`) are in place.
**Production is a harder call**: this test's whole point is provoking a
real 409 by racing two writes, which means deliberately creating conflicting
state on a live system. `frontend/e2e-prod/` today is strictly non-destructive
(one narrow, self-cleaning device-grant mint/revoke is the only write, see
`kid-device-grant.spec.ts`). Racing two devices against real production
reading-state is a meaningfully different risk profile — this should be a
deliberate decision with the team, not something to add unilaterally. My
recommendation: local and staging only; leave production out of scope for
this specific check unless the team decides otherwise.

## Suggested first PR scope

1. `frontend/e2e-real/reader-conflict-real.spec.ts`: the two-context recipe
   above, both resolution paths, against local Postgres + seeded uvicorn.
2. Once green and stable, consider a `frontend/e2e-staging/` equivalent
   using the seeded staging fixture. Hold off on anything for
   `frontend/e2e-prod/` pending an explicit decision.

`#ASSUME: concurrency: two Playwright BrowserContexts hitting the same
reading-state row nearly simultaneously is what "device A wrote first, B
is stale" means here; if both PUTs race close enough that ordering is
nondeterministic, the test needs an explicit wait (e.g. confirm device A's
choice via a completion signal) before firing device B's write, or the test
will be flaky rather than deterministically reproducing the conflict.
#VERIFY: whoever implements this should run it several times locally before
trusting it, exactly as this session did for the ratings/moderation
real-backend specs.`
