<!--
SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
SPDX-License-Identifier: MIT
-->

# Remediation Plan: Comprehensive Review 2026-07-17

**Source:** `docs/reviews/comprehensive-review-2026-07-17.md` (review at HEAD `7ae93fc`, v0.7.0).
**Goal:** close every Tier 1-3 finding and the high-value Tier 4 items in small,
independently shippable PRs, each with tests that pin the fixed behavior.
**Finding IDs** (SEC-*, UX-*, ARCH-*) refer to the review document; action IDs
(A1-A14) refer to its roadmap section.

---

## Ground rules for every PR in this plan

- One theme per PR; feature branches named per the CLAUDE.md table; Conventional
  Commit titles; signed commits.
- Behavior fixes land with a test that fails on the old code (regression pin).
  Where the review found tests pinning the *wrong* behavior (classifier
  silence), the PR must invert those tests, not delete them.
- Any PR that touches `api/schemas.py` or a router regenerates the frontend
  client (`npm run generate-client`) and commits the diff in the same PR, or
  the contract CI job fails.
- RAD tags (`#CRITICAL`/`#ASSUME`/`#EDGE` + `#VERIFY`) on new timing,
  concurrency, and security assumptions; this plan creates several (sweep
  timing, CAS claims, lockout counters).

---

## Status map

Legend: [x] done · [~] partial (rest blocked/deferred, see notes) · [ ] not started.

| PR | Title | Closes | Size | Depends on | Status |
| --- | --- | --- | --- | --- | --- |
| P1 | Generation worker-death resilience | ARCH-H1, ARCH-H2 (A1) | L | none | [x] |
| P2 | Moderation classifier degraded signal | ARCH-H3 (A2) | M | none | [x] |
| P3 | Renovate coverage for image digests + dead rules | ARCH-H4, part ARCH-L-TEST (A3) | S | none | [x] |
| P4 | Kid-route credential binding | SEC-F1, SEC-F2 (A7) | M | none | [x] |
| P5 | Offline library shelf | UX-K1 (A4) | M | P4 | [x] |
| P6 | Reader text-size control + wire `tts_enabled` | UX-K2 (A5) | M | none | [~] text-size control shipped; `tts_enabled` left as its documented deliberate deferral (no read-aloud yet) |
| P7 | Guardian pipeline visibility + auto-assign on publish | UX-G1, UX-G2 (A6) | M | none | [ ] blocked: auto-assign needs a schema migration threading requested_by_profile_id request->concept->storybook (no such link exists) |
| P8 | PIN lockout + Redis principal-keyed rate limiting | SEC-B1, SEC-B2 (A8) | L | none | [ ] |
| P9 | Frontend auth hygiene (PKCE, sourcemaps, cache purge) | SEC-F3, SEC-F4, SEC-F5 (A9) | M | none | [~] sourcemaps + cache purge done; PKCE (SEC-F3) deferred (reworks hash-based recovery detection, needs a live Supabase project to verify) |
| P10 | Cover staleness escape + queue retry policy | ARCH-M1, ARCH-M2 (A10) | M | P1 | [ ] blocked: StorybookVersion has no updated_at/cover_started_at; a reliable staleness check needs a schema migration |
| P11 | Backlog re-triage + doc corrections | A11 | S | none | [x] |
| P12 | Evaluator depth cap + schema_version gate | ARCH-M9, ARCH-M6 (A12) | M | none | [~] evaluator depth cap (ARCH-M9) done; schema_version reader gate (ARCH-M6) not started |
| P13 | Offline sync robustness (locks, conflicts store, IDB) | ARCH-M4, ARCH-M5 (A12) | M | P5 | [~] cross-tab replay lock + IDB blocking callbacks done; durable conflicts store (data-loss-on-tab-close) deferred (touches the delicate resolution flow) |
| P14 | Dev-loop and CI-gate hygiene | ARCH-M10, ARCH-M11, jsx-a11y (A13) | S | none | [~] nox extras + 3.10 drop + codecov + stale ignore done; jsx-a11y deferred (plugin peer range excludes eslint 10) |
| P15 | UX polish batch 1 (kid surface) | UX-K3, UX-K4, UX-K6, UX-K7 (A14) | S | none | [x] |
| P16 | UX polish batch 2 (adult surfaces + tokens) | UX-C1, UX-C2, UX-A1, UX-A3, UX-G4 (A14) | M | none | [x] |
| P17 | Progress semantics (finished state) | UX-K5 | M | P12 | [x] |
| P18 | Backend middleware hygiene | SEC-B3, SEC-B4, SEC-B6 | S | none | [x] |
| P19 | Admin master library (browse/re-review all stories) | new (see below) | M | none | [x] |

### P19: admin master library (delivered)

Surfaced while answering "does the admin have a master library page?" **No** (at
the time): the review queue (`GET /review-queue`, `AdminConsolePage` at `/admin`)
listed only `status == "in_review"` storybooks, so once a story was
approved/published or archived it left the queue with no way to browse back to
it. The detail path was already status-agnostic (`_load_admin_story` loads any
status; `ReviewDetailPage` renders a published story if navigated to directly),
so only a listing + entry point was missing. Delivered:

- Backend: admin-only `GET /v1/admin/storybooks` listing every storybook in any
  status (optional status filter), newest activity first, bulk-loaded like
  `get_review_queue`. New `StorybookSummary` / `StorybookLibraryView` schemas.
- Frontend: an `/admin/library` page with status-filter chips (nav link in
  `AdminShell`), each row linking to the existing `ReviewDetailPage`.

**Delivered in the 2026-07-17 implementation pass:** P1, P2, P3, P4, P11, P12
(depth cap), P14, P15, P18 fully; P9 and P12 partially. Every shipped change
carries regression tests and passed lint + typecheck; the backend unit suite and
the affected frontend suites are green. Blocked items (P7 auto-assign, P10 cover
staleness) require Supabase schema migrations that cannot be applied or
integration-tested from this repo alone; P9's PKCE flip and P14's jsx-a11y are
deferred for the environment/compatibility reasons noted above.

Suggested waves (PRs within a wave are independent and can run in parallel):

- **Wave 1 (reliability + safety):** P1, P2, P3, P11
- **Wave 2 (kid experience + core loop):** P4, P6, P7, P18
- **Wave 3 (security hardening):** P5, P8, P9, P10
- **Wave 4 (correctness + polish):** P12, P13, P14, P15, P16, P17

P11 runs in Wave 1 because its re-triage output may add PRs to this plan.

---

## Wave 1: reliability and safety

### P1. `fix(generation): survive hard worker death without stranding or double-executing jobs`

Closes ARCH-H1 and ARCH-H2 together: they share `generation/queue.py`, and the
fix for one changes the invariants the other depends on. Branch `fix/generation-worker-death`.

**Changes:**

1. `api/generation.py:_enqueue_safely` (line 160): pass `rq_job_id=job_id` so
   every enqueue path shares one RQ identity and `unique=True` dedupe applies
   globally. Catch `DuplicateJobError` as a no-op (row already queued).
2. `generation/worker.py:_load_and_start_job` (lines 640-648): replace the
   unconditional status write with a compare-and-set claim
   (`UPDATE ... SET status='running' WHERE id=:id AND status='queued'`); if no
   row updated, log `job.claim_lost` and return without executing. This makes a
   double-delivery harmless regardless of how it arose, which is the durable
   backstop even if the identity fix (change 1) is ever regressed.
3. `generation/queue.py:requeue_stranded_jobs` (lines 172-190): also select
   `status == "running"` rows with `updated_at < now - (generation_job_timeout_seconds + margin)`.
   Mark them `failed` with `error="interrupted: worker died"` (mirroring the
   `finally` guard at `worker.py:973-992`), emit the pipeline event, commit.
   Do NOT auto-re-enqueue these (the job may already have spent provider
   budget); recovery is the operator/guardian retry in P10. Return an accurate
   count that excludes `DuplicateJobError` no-ops.
4. `api/generation.py`: add admin-only `POST /v1/admin/generation-jobs/{id}/force-fail`
   (gated on `is_admin`) applying the same interrupted transition to a
   `queued`/`running` row. This is the escape hatch for a wedged family cap;
   without it two stranded rows block a family forever.

**Tests:** sweep marks a stale `running` row failed and leaves a fresh one
alone; return count excludes duplicates; CAS claim skips an already-`running`
and a terminal row; integration (existing Redis testcontainer) proves
original-enqueue-then-sweep yields exactly one execution; force-fail restores
enqueue capacity. Regenerate the client for the new endpoint.

**Acceptance:** a `kill -9` of the worker mid-job can no longer permanently
consume a family's generation cap, and a worker restart after a long outage
executes each queued row exactly once.

### P2. `fix(moderation): surface classifier outages as degraded findings`

Closes ARCH-H3. Branch `fix/moderation-classifier-degraded`.

**Changes:**

1. `moderation/classifiers.py`: on HTTP/parse failure of a classifier
   (`:74`, `:161-162` and the Perspective equivalent), and when a key is unset
   while the tier requires it, emit a structured advisory `Finding` of a new
   kind `classifier_degraded` (severity advisory, not BLOCK) carrying the
   classifier name and reason, instead of contributing zero findings silently.
2. Thread that finding into the moderation report so the review surface renders
   a visible "automated net was down for X" banner
   (`api/review_surface.py` / `moderation/insights.py` as applicable).
3. Frontend `admin/ReviewDetailPage.tsx`: render the degraded banner distinctly
   from content findings so a reviewer never mistakes a degraded report for a
   clean one.
4. Decide policy for the all-degraded case: recommend the report still reaches a
   human (mandatory-approval ADR unchanged) but is flagged, rather than
   auto-holding, to avoid a provider outage stalling the whole pipeline. Record
   the decision inline.

**Tests:** invert `tests/unit/test_moderation_classifiers.py:49, 490` (which
currently assert silence) to assert a `classifier_degraded` finding on
failure and on unset-key; report-assembly test shows the marker propagates.

### P3. `chore(renovate): manage image digests and remove dead rules`

Closes ARCH-H4 and the Renovate half of ARCH-L-TEST. Branch `chore/renovate-digest-coverage`.

**Changes:** add `"dockerfile"` and `"docker-compose"` to
`renovate.json:enabledManagers`; add a `customManagers` (regex) entry for the
nginx digest embedded in `ci.yml`; add `"pre-commit"` to `enabledManagers` so
the ruff hook version tracks the lock (fixes the 0.14.6 vs 0.15.20 skew); fix
the pep621 `matchDepTypes` values to the ones the manager actually emits and
resolve the `:preserveSemverRanges` vs `rangeStrategy: bump` conflict; correct
the now-true `Dockerfile:31` comment. **Verify:** dry-run Renovate config
(`renovate-config-validator`) in CI or locally.

---

## Wave 2: kid experience and the core loop

### P4. `fix(kid): bind kid routes to a route-matching child session`

Closes SEC-F1 and SEC-F2 (shared root cause: kid routes fall back to the broader
guardian bearer instead of requiring the child session for that profile).
Branch `fix/kid-route-credential-binding`.

**Changes:**

1. `hooks/useApi.ts:243-275`: on a kid route, do NOT fall through to the
   guardian bearer. Require a child session whose `profileId` matches the route
   param; if absent, redirect to the picker (re-mint, re-prompt PIN) rather than
   silently authorizing with guardian scope.
2. `reader/ReaderRoute.tsx:28-31` + `reader/ReaderPage.tsx:168-195`: gate the
   render on `getValidChildSession()?.profileId === routeProfileId(pathname)`
   (predicate exists at `auth/childSession.ts:180`). Refuse a cross-profile
   read even when the storybook is in the offline cache.
3. `offline/db.ts`: stamp cached reading-state records with the minting
   session's `profileId`; `getReadingState` refuses a record whose stamp does
   not match the active child session.
4. Backend defense-in-depth: confirm the reading-state read endpoint authorizes
   the child principal against the path `profile_id` (per the review the write
   path already 403s; verify the read path and add the check if missing).

**Tests:** frontend unit for the interceptor (kid route + guardian-only session
redirects, does not authorize); reader route guard test; offline db stamp
mismatch test; backend integration reusing the `stranger`/sibling fixtures for
the read path.

**Acceptance:** editing the URL to a sibling's `profileId` on a shared device
reaches neither the server nor the local cache for that sibling, including for a
PIN-protected profile.

### P6. `feat(reader): text-size control and functional tts_enabled toggle`

Closes UX-K2. Branch `feat/reader-legibility`. Note `tts_enabled` is already in
`api/schemas.py` (lines 819, 839, 861, 1497, 1519) and on the profile model, so
the API surface exists; the gaps are the guardian control and any reader use.

**Changes:**

1. `reader/ReaderChrome.tsx`: add an A / A+ / A++ text-size control that scales
   `PassageText` via a CSS custom property; persist the choice per profile
   (localStorage keyed by profileId is sufficient; it is a preference, not a
   security boundary). Honor `prefers-reduced-motion` already respected
   elsewhere.
2. `design-system/.../PassageText.css`: drive the fixed 18/20px sizes from the
   custom property with a sensible min/max.
3. `guardian/ProfileFormDialog.tsx` (~line 96): add the missing form control for
   `tts_enabled` (the field is already sent; this wires the toggle the comment
   says is absent).
4. TTS itself: **scope decision.** If in-scope now, add a read-aloud button in
   the reader using the Web Speech API behind the `tts_enabled` flag; if
   deferred, keep the toggle but disable it with a "coming soon" hint and file
   the roadmap item, so the field is no longer dangling. Recommend shipping the
   text-size control now and the toggle-wiring now, TTS as a fast-follow.

**Tests:** reader renders and persists the size choice; profile form round-trips
`tts_enabled`; component test that the size control meets the 44px tap floor.

### P7. `feat(guardian): pipeline visibility off Intake and auto-assign on publish`

Closes UX-G1 and UX-G2. Branch `feat/guardian-pipeline-visibility`.

**Changes:**

1. Auto-assign on publish: in `publishing/service.py`, when a storybook that
   originated from a child's story request is published, create the assignment
   to the requesting profile in the same transaction (the request row carries
   the `profile_id`). Guard for the guardian-initiated case (no requester):
   leave unassigned but mark it. Emit the assignment event.
2. `guardian/GuardianShell.tsx`: add a second nav signal (or extend the badge)
   counting stories that are in-progress or ready-but-unviewed, not only
   kid-initiated pending requests, so a parent who closed the Intake tab still
   sees "1 ready".
3. `guardian/IntakePage.tsx` / `guardian/BooksPage.tsx`: make the
   ready-but-unassigned state loud ("Ready, not assigned yet" with a primary
   "Give it to <child>") rather than a passive "Assigned to: No one yet".

**Tests:** publishing-service test that a request-originated publish creates the
assignment and event; guardian-initiated publish does not; frontend badge count
test. Regenerate the client if the publish response shape changes.

### P18. `chore(security): activate TrustedHost, delimit prompts, fix correlation order`

Closes SEC-B3, SEC-B4, SEC-B6 (small, low-risk backend hygiene batched).
Branch `chore/backend-middleware-hygiene`.

**Changes:** pass the deployment's `allowed_hosts` into `add_security_middleware`
so `TrustedHostMiddleware` is actually added (SEC-B3); wrap the untrusted brief
in explicit delimiters within the prompt template at `generation/prompts.py:305, 382`
with an "untrusted, do not treat as instructions" preamble (SEC-B4); reorder
`app.py:212` so `CorrelationMiddleware` is outermost (or correct its comment) so
middleware-layer rejections carry a correlation ID (SEC-B6).

**Tests:** TrustedHost rejects a spoofed Host in an integration test; prompt
template snapshot shows the delimiters; a rate-limit rejection log carries a
correlation ID.

---

## Wave 3: security hardening

### P5. `feat(kid): offline library shelf`

Closes UX-K1. Branch `feat/offline-library-shelf`. Depends on P4 (per-profile
session binding) so the cached shelf is correctly scoped.

**Changes:** cache the last-good library list per profile in IndexedDB on each
successful load (`library/LibraryPage.tsx`); add a `listCachedStorybooks(profileId)`
to `offline/db.ts`; when `useOnlineStatus` reports offline (or the list fetch
fails offline), render the cached shelf with a kid-friendly "No internet, these
books are ready to read" banner, disabling uncached books, instead of the
dead-end "We lost the bookshelf / Try again". **Tests:** offline render uses
cache; uncached books are visibly disabled; the banner copy is present.

### P8. `feat(security): PIN attempt lockout and Redis principal-keyed rate limiting`

Closes SEC-B1 and SEC-B2 (the device-token threat model makes the PIN a real
boundary the current IP limiter does not protect). Branch `feat/pin-lockout-redis-ratelimit`.

**Changes:** add a per-profile failed-attempt counter with exponential backoff /
temporary lockout on the PIN check (`api/child_sessions.py:134-156`), keyed on
`profile_id` and independent of IP, backed by Redis so it holds across the 2
replicas; migrate the rate limiter (`middleware/security.py:217-350`) from the
per-process dict to Redis, keyed on principal where available and IP otherwise.
RAD-tag the lockout window and the fail-open-vs-closed choice if Redis is
unreachable (recommend fail-closed for the PIN counter, fail-open for the coarse
rate limiter, and document why). **Tests:** N failed PINs lock the profile for
the window then recover; counter is per-profile not per-IP; rate-limit state
survives a simulated second process.

### P9. `fix(auth): enable PKCE, drop public sourcemaps, purge caches on sign-out`

Closes SEC-F3, SEC-F4, SEC-F5. Branch `fix/frontend-auth-hygiene`.

**Changes:** pass `{ auth: { flowType: 'pkce' } }` to `createClient`
(`auth/supabaseClient.ts:101`) and update recovery-landing detection from the
hash to the `?code=` + `type=recovery` shape; set `vite.config.ts` sourcemap to
`'hidden'` (or `false`); on `signOut()` and on a device-grant 401,
best-effort `caches.delete('api-cache')` and clear the `reading_states` store.
**Tests:** auth-context recovery-flow test against the PKCE shape; a sign-out
test asserting the cache/store are cleared; build asserts no `.map` served
publicly.

### P10. `feat(covers): staleness escape hatch and bounded queue retries`

Closes ARCH-M1 and ARCH-M2. Branch `feat/queue-retry-and-cover-recovery`.
Depends on P1 (shares the staleness/timeout pattern).

**Changes:** treat `cover_status="generating"` older than the cover timeout as
re-enqueueable in `api/covers.py:65-66` (or include covers in the startup
sweep); add bounded `Retry(max=2, interval=[30, 120])` for provider-transient
exceptions in `generation/queue.py` and `covers/worker.py` (the worker already
distinguishes transient errors), OR add a guardian-visible retry action on a
`failed` generation job plus a documented fail-fast policy. Recommend both: RQ
retry for transient provider blips, guardian retry for terminal failures.
**Tests:** stale `generating` cover re-enqueues; a transient exception retries
then succeeds; a permanent failure stops at the bound and exposes the retry
action.

---

## Wave 4: correctness and polish

### P11. `docs(security): re-triage backlog and correct stale status map`

Closes A11. Branch `docs/backlog-retriage`. Re-verify each remaining tracked
finding (H1-H4 delivery cluster, M-series) against current code; update the
status map in `security-hardening-plan-2026-07.md` (mark C1 and K1 done, and
whatever else the re-triage confirms); if the sweep finds a still-open item not
covered by P1-P18, add a PR row to this plan. Fix the `CLAUDE.md` router count
(14 vs 21) and the `noxfile.py` MyPy reference via `docs/template_feedback.md`
per the project's template-feedback rule. No code changes.

### P12. `fix(storybook): depth-cap the condition evaluator and gate schema_version`

Closes ARCH-M9 and ARCH-M6. Branch `fix/evaluator-depth-and-schema-gate`.
Add an explicit recursion-depth cap in `validate_condition`
(`storybook/condition.py`) that raises `ValidationError` on over-deep
conditions, with an adversarial Hypothesis/handwritten test (the current
strategy caps at `max_leaves=8` and never exercises the limit); check
`schema_version` in `ReaderPage.load()` (`api/readerApi.ts:97`) and route
unsupported versions to the error phase; add a test asserting the player enums
(`player/types.ts`) against `schema/storybook.schema.json` so drift fails CI.

### P13. `fix(offline): cross-tab locks, durable conflicts, IDB upgrade safety`

Closes ARCH-M4 and ARCH-M5. Branch `fix/offline-sync-robustness`. Depends on P5.
Wrap replay in `navigator.locks.request('cyo-replay', ...)`
(`hooks/useReplayOnReconnect.ts`); move 409-conflicted writes to a `conflicts`
store instead of deleting them from durable storage (`offline/sync.ts:229-278`);
add `blocking: (..., db) => db.close()` and a `blocked` surface to the IDB open
(`offline/db.ts:55-76`); evict other cached versions of the same story id on
`cacheStorybook`. **Tests:** two-tab replay does not manufacture conflicts;
a conflicted write survives a tab close; a `DB_VERSION` bump does not hang a new
tab.

### P14. `chore(dev): fix nox extras, extend coverage gate, add jsx-a11y`

Closes ARCH-M10, ARCH-M11, and the a11y-lint item. Branch `chore/dev-loop-hygiene`.
Change nox sessions to install `.[dev,api]` and drop the 3.10 legs so the
documented pre-push parity loop runs (`noxfile.py`); add `api/deps.py` and
`publishing/**` to the codecov safety-critical component, or delete the dead
`[tool.test-coverage-agent]` table; add `eslint-plugin-jsx-a11y` to
`frontend/package.json` and wire it into the flat config so the existing
accessibility work is regression-protected; remove the stale `utils/financial.py`
per-file-ignore.

### P15. `fix(kid): kid-surface polish batch`

Closes UX-K3, UX-K4, UX-K6, UX-K7. Branch `fix/kid-surface-polish`. Style the
`.picker-tile__add-link` class (currently has no CSS rule) as a 44px pill or the
@ds link-button (UX-K4); quote `request_text` above each status row so pending
ideas are distinguishable (UX-K3); add an "ask a grown-up" escape after repeated
PIN failures (UX-K6); raise the reader "Leave" button to the 44px floor
(`reader.css:34`) (UX-K7).

### P16. `fix(ui): adult-surface polish and token decision`

Closes UX-C1, UX-C2, UX-A1, UX-A3, UX-G4. Branch `fix/adult-surface-polish`.
Standardize inline Retry over "Please reload" dead-ends
(`StoryRequestQueue.tsx:266`, `BooksPage.tsx:150`, `ProfilesPage.tsx:62`)
(UX-C1); resolve the `--color-ink-muted` AA decision, either raise the shade to
AA-safe or re-class the load-bearing hints to `--color-ink-secondary` (UX-C2);
auto-advance the admin review queue to the next flagged item and show queue
position (`admin/ReviewDetailPage.tsx`) (UX-A1); add age band + waiting-since to
queue rows and raise the moderation dashboard buttons to the 44px floor (UX-A3);
humanize the raw enum tokens in the kid-request approval form
(`StoryRequestQueue.tsx:355-380`) (UX-G4).

### P17. `feat(reader): real completion semantics`

Closes UX-K5. Branch `feat/reader-completion`. Depends on P12 (shares reader
load-path changes). Track per-book completion (any ending reached renders
"Finished!"); compute any exploration percentage against the reachable node set
(ideally server-side so both runtimes agree), not raw `visited / all nodes`, so
a finished branching story no longer shows "3 of 24 pages explored".

---

## Verification and exit criteria

- Every PR: `uv run pytest --cov=src --cov-fail-under=80`, `ruff check`,
  `basedpyright src/`, `bandit`, and (for frontend PRs) `npm run lint`,
  `typecheck`, `test:run`, `build` all green; contract job green (client
  regenerated where the API changed).
- Tier-1 exit: a chaos test (kill the worker mid-job) leaves no family locked
  and no double execution; a forced classifier outage renders a visible
  degraded banner in the review UI; Renovate opens a digest-bump PR.
- Tier-2 exit: URL-editing to a sibling profile on a shared device is refused
  online and offline; an offline kid sees their downloaded shelf; a text-size
  change persists; a published request-originated story appears in the
  requesting child's library without a manual assign.
- Tier-3 exit: PIN lockout survives across replicas; PKCE flow completes; caches
  clear on sign-out.
- Close-out: update the status map above and the tracked hardening plan; move
  any residual items from P11's re-triage into a follow-up plan.

---

*Derived from the 2026-07-17 comprehensive review. Sizes are rough
(S: under a day, M: 1-2 days, L: 2-4 days) and assume the existing test
infrastructure. Sequence is a recommendation, not a hard dependency graph;
only the explicit "Depends on" edges are load-bearing.*
