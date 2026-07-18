<!--
SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
SPDX-License-Identifier: MIT
-->

# Comprehensive Review: Security, UX, and Design (2026-07-17)

**Reviewed at:** HEAD `7ae93fc` (v0.7.0)
**Scope:** whole repository, backend (`src/cyo_adventure/`), frontend
(`frontend/src/`), infrastructure, tests, docs.
**Method:** four parallel read-only review passes (backend security, frontend
security, UX and product design, architecture and infrastructure), each
verifying claims line by line against source, then cross-referenced against the
existing red-team backlog in `docs/security/red-team-design-review-2026-07.md`
and `docs/planning/security-hardening-plan-2026-07.md`.

> This document treats all findings as internal engineering notes. Nothing here
> was exploited; every finding was confirmed by reading the code.

---

## Executive summary

This is an unusually disciplined codebase for its age. The security posture is
mature and defense-in-depth: JWT verification pins algorithms and rejects `none`
and HS-family confusion, three token families use distinct secrets and
audiences, IDOR is closed consistently at the auth boundary rather than per
query, the condition DSL is whitelist-validated with no dynamic evaluation
(zero `eval`/`exec`/`subprocess`/`verify=False` in the tree), PINs are stored
with PBKDF2-HMAC-SHA256 at 600k iterations, and config fails closed on unset or
placeholder secrets. The frontend has no HTML-injection sinks at all, redacts
tokens in logs at a single choke point, and classifies 401s so a dead child
token can never tear down a live guardian session. Workflows are SHA-pinned with
minimal permissions, the Docker runtime is distroless and non-root, and the test
tier runs the real stack against real Postgres.

The highest-impact residual issues are **not** open security holes. They cluster
in three themes:

1. **Hard worker death is not fully modeled in the generation pipeline.** A
   SIGKILL/OOM strands jobs at `running` forever, the reclaim sweep can
   double-execute jobs, and cover generation has an unrecoverable stuck state.
2. **The kid experience breaks at its edges.** Offline kids cannot reach books
   they already downloaded, the youngest readers have no text-size or read-aloud
   support, and the request-to-read loop can silently stall at the unassigned
   step.
3. **A few safety and hygiene controls fail quietly.** External moderation
   classifiers fail open with no `degraded` signal to the reviewer, and the
   security-hardening plan's status map is stale (several tracked items have
   since shipped, so the map no longer reflects reality).

There are no Critical findings and no open High-severity security holes in the
current tree. The High-severity items below are reliability and child-safety
robustness issues.

---

## Part 1: Status of the tracked red-team backlog

The backlog (`red-team-design-review-2026-07.md`) and its plan
(`security-hardening-plan-2026-07.md`) predate a run of hardening PRs (#228
child-scoped kid tokens, #247 device-authorized kid access per ADR-014, #233
per-profile PINs, #232 parental re-auth, #258 password recovery). **The plan's
status map still lists every finding as "not started," which is now incorrect.**
Fixing that drift is itself an action item (see A11).

Confirmed from current code:

| ID | Title | Current status (verified) |
| --- | --- | --- |
| C1 | `environment` defaults to unverified auth stub (fail-open) | **Fixed.** `core/config.py` raises at startup on an unset deployment tier, weak/placeholder signing secrets (<32 bytes), and missing OIDC; the dev auth stub raises `ConfigurationError` if constructed outside local (`api/deps.py:89-98`). |
| K1 | Children share the guardian token in R1 | **Fixed.** Children now have their own principal: child HS256 session tokens (distinct secret and audience) and DEVICE tokens (ADR-014), each scoped to one profile with `is_admin`/`profile_ids` invariants forced clear at construction (`api/deps.py:136-169, 542-555`). |
| L2 | Child free-text templated into prompt with no delimiting | **Still open** (re-filed as SEC-B4 below). |
| L5 | Health endpoints disclose exact version | Partially addressed: health responses no longer leak DSN/host; version fingerprinting on the public probes should still be re-checked. |

The remaining tracked IDs (H1-H4 child-safety-delivery cluster, M-series) were
**not** re-verified end to end in this pass and must be re-triaged against
current code rather than trusted from the stale map. Recommend a short
re-triage sweep as the first hardening task.

---

## Part 2: Security findings (new / re-filed)

### Backend

**SEC-B1 (Medium). Profile PIN has no brute-force lockout, now reachable by a long-lived device token.**
`api/child_sessions.py:134-156` deliberately implements no per-profile attempt
counter, on the stated assumption that the mint endpoint always sits behind an
authenticated guardian. ADR-014 phase 2 breaks that assumption: the endpoint is
now reachable by a DEVICE principal (`:83-89`, `:120-132`), a 90-day shared-tablet
token. That is exactly the scenario where the PIN *is* the boundary between
siblings on one device. A 4-digit PIN is 10^4 combinations; the only throttle is
the global in-memory 60 rpm/IP limiter, and the device-token holder controls the
client. **Fix:** add a per-profile failed-attempt counter with backoff/lockout,
keyed on `profile_id` and independent of IP.

**SEC-B2 (Low, tracked #71). Rate limiter is in-memory, per-process, IP-keyed.**
`middleware/security.py:217-350`. Counters live in a per-process dict, so with
`REPLICAS=2` (`docker-compose.prod.yml:37`) the effective ceiling doubles and
resets on every deploy. Keyed on IP, not principal, so it is weak against
authenticated or distributed abuse, and it is the *sole* throttle behind the PIN
check in SEC-B1. **Fix:** back the limiter with the Redis already in the stack;
key on principal where available. Address together with SEC-B1.

**SEC-B3 (Low). `TrustedHostMiddleware` is never activated.**
`app.py:221` calls `add_security_middleware` without `allowed_hosts`, so the Host
/ `X-Forwarded-Host` header is unvalidated (`security.py:588-592`). Low risk
behind nginx, but no defense-in-depth against Host-header spoofing. **Fix:** pass
the deployment's allowed hosts. (CORS `allow_origins` being empty is correct:
prod is same-origin via `/api`.)

**SEC-B4 (Low, re-files L2). Guardian/child free text enters LLM prompts without explicit delimiting.**
`generation/prompts.py:305, 382` interpolate the guardian/child-authored brief
into the prompt's user region with no "treat the following as untrusted data"
fencing. Strongly mitigated (submission-time PII guard + Stage-0 classifiers,
then the deterministic validator gate, an independent moderation provider, and
mandatory human approval all sit between a brief and any reader), and there is no
format-string injection (`.replace()`, not `.format()`). Residual risk is wasted
generation spend and over-reliance on the gate. **Fix:** wrap the untrusted brief
in explicit delimiters in the template.

**SEC-B5 (Informational). SSRF middleware guards nothing today; egress is config-bound.**
`SSRFPreventionMiddleware` (`security.py:513-542`) inspects only inbound query
params for embedded URLs, and no endpoint accepts a URL param, so it protects
nothing currently, while the real outbound surface (provider and R2 hosts) is
config-only (`covers/storage.py:21-23`). Acceptable as-is; note the middleware is
not the control protecting egress, and any future "import-by-URL" field needs its
own guard (the code already flags this at `security.py:523-527`).

**SEC-B6 (Informational). Correlation middleware ordering contradicts its comment.**
`app.py:212` adds `CorrelationMiddleware` innermost, so rate-limit/body-size/SSRF
rejections are emitted without a correlation ID, despite the comment claiming
correlation "must wrap everything else." Observability gap only. **Fix:** reorder
so correlation is outermost, or correct the comment.

### Frontend

**SEC-F1 (Medium). Offline reader is unauthenticated per-profile: URL editing reaches any cached story and any sibling's reading state, including PIN-protected profiles.**
`reader/ReaderRoute.tsx:28-31` (self-documented "stays unauthenticated for now",
the tracked C4a-2 work), `reader/ReaderPage.tsx:168-195`, `offline/db.ts:94-110`.
On a shared tablet with a device grant, child A opens
`/read/<profileB-id>/<storybook>/<version>` by editing the URL. `ReaderPage.load()`
reads the storybook cache-first from IndexedDB and never contacts the server when
cached, then loads `getReadingState(profileId)` keyed purely on the URL param.
Child A reads B's book, sees B's progress, and overwrites B's local state, even
for a PIN-protected sibling (the PIN is only enforced at the picker's mint call).
Server-side writes still 403. **Fix:** gate the reader render on
`getValidChildSession()?.profileId === routeProfileId(pathname)` (the predicate
exists at `auth/childSession.ts:180`); store the minting session's profileId with
cached reading states and refuse cross-profile reads.

**SEC-F2 (Medium). Profile PIN is bypassable by deep link when a guardian bearer is present.**
`hooks/useApi.ts:243-275` (guardian-token fallthrough on kid routes),
`kid/ProfilePickerPage.tsx:141-151` (comment admits the fallback "would silently
bypass the lock"). When a guardian is signed in on the device, a sibling typing
`/library/<pin-profile-id>` gets served the full library because the interceptor
falls through to the guardian bearer, whose scope covers all family profiles;
the PIN prompt never shows. **Fix:** same root cause as SEC-F1: hard-require a
route-matching child session on kid routes instead of falling back to the
guardian token, or make PIN enforcement a server-side property of the profile.
Fix SEC-F1 and SEC-F2 together.

**SEC-F3 (Medium). Supabase auth uses the deprecated implicit flow; PKCE not enabled.**
`auth/supabaseClient.ts:101` creates the client with no `auth.flowType: 'pkce'`,
so OAuth and password-recovery links land with `#access_token=...` in the URL
fragment, briefly observable by extensions or any future analytics script (DSN
env vars are already plumbed). **Fix:** pass `{ auth: { flowType: 'pkce' } }` and
verify the recovery-landing detection against PKCE's `?code=` + `type=recovery`
shape (`AuthContext` logic is currently coupled to the hash).

**SEC-F4 (Low). Production source maps are shipped.**
`vite.config.ts:158-161` (`sourcemap: true`) exposes full source, including the
security comments describing auth seams. **Fix:** `sourcemap: 'hidden'` with
upload to an error tracker, or `false`.

**SEC-F5 (Low). Authenticated data persists at rest after sign-out / grant revocation.**
Workbox `api-cache` (NetworkFirst, 7-day TTL) caches authenticated GETs and
IndexedDB blobs are never purged; the cache key is correctly partitioned by a
SHA-256 of the auth header (good), but nothing evicts children's names, story
content, or reading states on sign-out or grant revocation. Readable via DevTools
on a returned or hand-me-down device. **Fix:** best-effort `caches.delete('api-cache')`
and clear the `reading_states` store on `signOut()` and on a device-grant 401.

**SEC-F6 (Low). Adult step-up gate is bypassed for OAuth-only guardians with no server counterpart.**
`auth/AdultGate.tsx:113-142` passes OAuth users through with only a `console.warn`
and is self-documented as "a client-side deterrent, not a security boundary."
OAuth will be the majority sign-in path at public launch, so a kid reaching an
adult tab faces no challenge. **Fix (per the file's own notes):** an onboarding
PIN for OAuth guardians plus a backend-minted short-lived re-auth grant demanded
by the approve/publish endpoints. Schedule before Track 2.

**SEC-F7 (Low, defense-in-depth). Four bearer credentials live in script-readable localStorage.**
`auth_token`, the Supabase session (including refresh token), child session, and
device grant. No XSS sink exists today, so this is contingent on a future XSS or
malicious dependency, but it would then yield full account takeover. **Fix:**
shorten guardian access-token TTL, enable revoke-on-password-change, apply a
strict `script-src 'self'` CSP at the hosting layer.

---

## Part 3: UX and product-design findings

`docs/qa/naive-ux-reports/` is empty (only `.gitkeep`); known items live in the
2026-07-11 handoff doc and inline comments. F1 and G2 from that doc are fixed;
the `--color-ink-muted` AA miss and the @ds promotions remain open.

### Kid surface

**UX-K1 (High). Offline kids cannot reach their downloaded books.**
`library/LibraryPage.tsx:191-210`, `offline/db.ts` (has `getCachedStorybook` but
no way to list cached books), `reader/ReaderChrome.tsx` (only `useOnlineStatus`
consumer). Story blobs cache on first read and the reader opens cache-first, but
the library list is network-only: a child on a plane taps their profile and gets
"We lost the bookshelf / Try again" with a button that can never succeed, while
yesterday's downloaded book sits in IndexedDB with no door to it. **Fix:** cache
the last-good library list per profile; on offline, render the cached shelf with
a "No internet, these books are ready to read" banner and disable uncached books.
At minimum branch the error copy on `useOnlineStatus`.

**UX-K2 (High). No read-aloud and no text-size control for the 4-6 end of the range.**
`reader/Reader.tsx`, `design-system/.../PassageText.css` (fixed 18/20px),
`guardian/ProfileFormDialog.tsx` (~line 96: "No form control backs this field"
for `tts_enabled`). The product targets ages ~4-10 but the reader has zero
legibility accommodations, and the `tts_enabled` flag is plumbed through the API
with neither a guardian control nor a reader implementation. A pre-reader cannot
use the app without an adult reading every passage. **Fix:** ship an A/A+
text-size control in `ReaderChrome` (persisted per profile) as the cheap win;
treat TTS as the roadmap item it appears to be, and wire or remove the dangling
`tts_enabled` field.

**UX-K3 (Medium). A kid's "My requests" rows are indistinguishable.**
`library/RequestStory.tsx:250-261` renders only the status label, so three
pending ideas all read "Waiting for a grown-up to say yes"; when one is declined
the child cannot tell which idea it was. The request text is already in the
payload. **Fix:** render a short quote of `request_text` above each status line.

**UX-K4 (Medium). Kid-facing recovery links are unstyled browser defaults.**
`kid/ProfilePickerPage.tsx` (lines 236, 253, 277, 293) and
`library/LibraryPage.tsx` (163, 166, 183, 202) use `className="picker-tile__add-link"`,
which **has no CSS rule anywhere in the tree**. "I am a grown-up" and "Back to
Who's reading?" render as tiny default-blue underlined links, well under the 44px
tap floor used everywhere else, on the exact error screens a stressed kid or
parent hits. **Fix:** style the class like `.picker-retry` (44px pill) or use the
@ds Button-as-link.

**UX-K5 (Medium). Reader progress bar misleads: a finished book can look 12% done.**
`reader/readerProgress.ts`, `library/BookCard.tsx`. Percent is `visited / all
nodes`, but a branching playthrough touches a fraction of nodes; the reader hides
the numeric label as a workaround, yet the library hero card shows "3 of 24 pages
explored" for a fully finished book. **Fix:** track per-book completion (any
ending reached renders "Finished!"); compute any exploration percentage against
the reachable set, ideally server-side.

**UX-K6/K7/K8 (Low).** PIN prompt has no "ask a grown-up" escape after repeated
failures (`ProfilePickerPage.tsx:301-363`); the reader "Leave" button is the one
kid control under the 44px floor (`reader.css:34`, `min-height: 40px`); the
conflict dialog's "Keep this device / Use the newest place" concept is abstract
for a 6-year-old (copy matches the design spec, so this is an iteration note).

### Guardian console

**UX-G1 (Medium). Pipeline status lives only on the Intake page; a guardian gets no signal when a story is ready.**
`guardian/GuardianShell.tsx` (nav badge counts only kid-initiated pending
requests), `guardian/IntakePage.tsx` (the only place the Generating/Waiting/
Approved/Failed pills exist, polling only while open). A parent who requests a
story and closes the tab is never told it finished. **Fix:** add an in-progress/
ready count to the Console home quick-links and/or a second nav badge; longer
term, a notification channel.

**UX-G2 (Medium). An approved story is not visibly connected to the child who asked, and assignment is an easy-to-miss manual step.**
`guardian/IntakePage.tsx` ("Assign more" on Approved rows), `guardian/BooksPage.tsx`
("Assigned to: No one yet"). If the guardian does not click through, the book a
child requested never reaches that child's library, while the child's own request
list still says "Yay! Your story is being made." **Fix:** auto-assign to the
requesting child on publish (the request carries the profile), or make the
unassigned state loud ("Ready, not assigned yet" + a primary "Give it to <child>").

**UX-G3 (Medium). "Request a story" vs "Story requests" name two different flows almost identically.**
`guardian/GuardianShell.tsx:108-137`. A guardian looking for the status of the
story they requested will plausibly open "Story requests" (the kids'-ideas review
queue) instead. **Fix:** rename to intent-revealing pairs, e.g. "New story" /
"Kids' ideas (3)", and cross-link the empty states.

**UX-G4/G5/G6/G7 (Low).** The kid-request approval form exposes raw enum tokens
(`prose`/`gamebook`, raw lengths) next to a humanized age band
(`StoryRequestQueue.tsx:355-380`); failed intake rows surface the raw pipeline
error string to parents (`IntakePage.tsx:371-382`, fine for R1, gate behind a
disclosure before external launch); dialog forms lose typed input on backdrop
click/Escape (`design-system/.../Dialog.tsx`); first-run has no "now request your
first story" continuation after the first profile, and the device-grant "This
device" section never explains *when* to do the handoff.

### Admin console

**UX-A1 (Medium). No queue flow-through: every decision round-trips to the list.**
`admin/ReviewDetailPage.tsx` (`runAction` navigates back to `/admin`). A reviewer
clearing 15 stories has no "next in queue," no position indicator, no keyboard
shortcuts. **Fix:** auto-advance to the next flagged item after a confirmed
action; show queue position in the detail header.

**UX-A2/A3 (Low).** Queue rows carry no triage metadata beyond title + severity
(no age band, no "waiting since", though `formatRelativeTime` exists elsewhere);
the moderation dashboard uses native unstyled buttons under the 44px floor and
renders findings as dense run-on sentences (`ModerationDashboardPage.tsx:254`).
The review detail surface itself is a model of the genre (coverage line,
unreachable-passage section, flagged-passage jump links, version diff) and worth
preserving.

### Cross-cutting

**UX-C1 (Medium). "Please reload" dead-end errors, inconsistent with sibling surfaces.**
`StoryRequestQueue.tsx:266`, `BooksPage.tsx:150`, `ProfilesPage.tsx:62` render
"...Please reload." as a dead-end alert, while IntakePage, AdminConsolePage, and
the kid surfaces all offer in-place retry. "Reload the tab" is an instruction, not
an affordance, and is unclear on a PWA/tablet. **Fix:** standardize on an inline
Retry button.

**UX-C2 (Medium). `--color-ink-muted` (4.20:1, below AA) carries load-bearing copy.**
`design-system/src/utilities.css` documents the AA miss and says "hint copy only,"
but `.cyo-text-muted` is used for the intake expectation subline ("Usually ready
in a few minutes," the main wait-anxiety reliever), submit-blocker hints, and
kid-surface labels. **Fix:** make the deferred token decision once: raise the
shade to AA-safe, or re-class the essential hints to `--color-ink-secondary`.

**UX-C3/C4/C5 (Low).** Loading states are bare text on adult surfaces vs branded
mascot loaders on kid surfaces (add a shared @ds skeleton);
`ModerationDashboardPage`'s 8-column table and `ReviewDetailPage`'s action bar
have no narrow-screen handling; toasts are the only success channel and vanish in
5s (fine for the row-removal case).

---

## Part 4: Architecture, pipeline, infrastructure, testing

### Pipeline robustness (highest impact)

**ARCH-H1 (High). A hard-killed worker strands jobs at `running` forever, and two stranded rows lock a family out of generation permanently.**
`generation/queue.py:172-178` (the sweep selects only `status == "queued"`),
`generation/worker.py:973-992` (the `finally` guard cannot run on SIGKILL/OOM),
`api/generation.py:80-85` (`MAX_ACTIVE_JOBS_PER_FAMILY = 2`, counting both
`queued` and `running`). An OOM-killed worker leaves the row `running` forever;
no sweep touches it, and because the family cap counts `running`, two such events
permanently block that family from enqueuing (409) with no operator surface to
clear it. **Verified.** **Fix:** extend `requeue_stranded_jobs` to also sweep
`running` rows older than the job timeout plus margin, marking them
`failed/interrupted`; and/or reconcile against RQ's `StartedJobRegistry` at
worker startup.

**ARCH-H2 (High). The reclaim sweep can double-execute jobs.**
`api/generation.py:160` (`_enqueue_safely` calls `enqueue_generation(job_id,
settings)` with no `rq_job_id`, so RQ mints a random id and `unique=False`),
`generation/queue.py:183` (the sweep re-enqueues with `rq_job_id=row_id`),
`generation/worker.py:640-648` (`_load_and_start_job` sets `running` with no
status guard). The original enqueue's random id is invisible to the sweep's
`rq_job_id=row_id` dedupe, so when the worker is down longer than the stale
window while Redis retains the queue, the restart re-enqueues every still-queued
row and each executes twice: duplicate LLM spend and two `persist_storybook`
calls racing on one row. **Verified.** **Fix:** pass `rq_job_id=str(job.id),
unique=True` on the *original* enqueue so all paths share one identity; add a
compare-and-set claim in `_load_and_start_job` (`UPDATE ... SET status='running'
WHERE id=:id AND status='queued'`).

**ARCH-H3 (High). External safety classifiers fail open silently.**
`moderation/classifiers.py:74, 161-162` (HTTP/parse errors log a warning and
contribute zero findings; both keys unset returns `[]`), with unit tests pinning
the silence. No `degraded` marker reaches the moderation report, so on an expired
key or provider outage every story reaches the human reviewer with a report
indistinguishable from genuinely clean, on a kids'-content pipeline where reviewer
calibration assumes the automated net ran. Mandatory human approval bounds but
does not eliminate the harm. **Verified.** **Fix:** emit an explicit `degraded`
finding per failed or unconfigured classifier so the review UI shows the net was
down; invert the tests that assert silence.

**ARCH-M1 (Medium). Cover generation has an unrecoverable stuck state after hard worker death.**
`covers/service.py:109-111` sets `cover_status="generating"` and commits before
calling the provider; `api/covers.py:65-66` treats a `generating` row as a
permanent no-op on re-request. A SIGKILL between those points leaves `generating`
forever, the admin retry affordance never appears, and no sweep covers
`cover_status`. **Fix:** treat `generating` older than the cover timeout as
re-enqueueable, or include covers in a startup sweep.

**ARCH-M2 (Medium). No retry policy anywhere in the queue layer.**
`generation/queue.py:129-135`, `covers/worker.py:29-35` never pass RQ's `Retry`,
and no endpoint re-runs a failed job. A transient provider 429/529 permanently
fails the job; the guardian's only recourse is a new job (another cap slot, lost
correlation). Fail-fast is defensible for cost control but is currently implicit.
**Fix:** bounded `Retry` for provider-transient exceptions (the worker already
distinguishes them), or a guardian-visible retry action plus a documented policy.

### Backend design

**ARCH-M3 (Medium). `api/schemas.py` is a 1,571-line coupling hub with an inverted dependency.**
It holds every router's models and imports from domain packages, while
`story_requests/screening.py:19` runtime-imports `StoryRequestFlag` back from it
(a domain-to-API inversion that becomes a real cycle the moment `schemas.py`
imports anything from `story_requests`). **Fix:** split schemas per router and
move shared enums down into the domain layer.

**ARCH-L (Low).** Existence-oracle inconsistency on cross-family story fetch
(`api/library.py:400-401` returns 403 where the module's docstring promises 404);
`parse_uuid` duplicated in three routers despite a shared helper; local response
models in `api/covers.py`/`api/health.py` undercut the schemas convention; doc
drift (`CLAUDE.md` says 14 routers, `app.py` wires 21; `noxfile.py` docstring
still says MyPy) belongs in `docs/template_feedback.md` per project rules.

### Frontend design

**ARCH-M4 (Medium). Offline replay has no cross-tab coordination and drops conflicted writes before the child resolves them.**
`offline/sync.ts:229-278` unconditionally dequeues a 409-conflicted write from
IndexedDB after latching the conflict; `hooks/useReplayOnReconnect.ts:9-14` uses
a per-hook `busy` ref, not `navigator.locks`. Two tabs interleave rebases and
manufacture spurious conflict dialogs; closing the tab before answering a genuine
dialog loses the queued write from durable storage. **Fix:** wrap replay in
`navigator.locks.request('cyo-replay', ...)` and move conflicted items to a
`conflicts` store instead of deleting.

**ARCH-M5 (Medium). IndexedDB schema bumps can hang all new tabs; no eviction ever runs.**
`offline/db.ts:55-76` registers no `blocked`/`blocking` callbacks and caches the
open promise, so at the next `DB_VERSION` bump a new tab waits forever while an
old tab holds the connection; blobs are cached forever with no LRU. A realistic
"app won't load" incident on cheap shared tablets. **Fix:** add `blocking: (...,
db) => db.close()` plus a `blocked` surface; evict other cached versions of the
same story id on write.

**ARCH-M6 (Medium). No `schema_version` gate on story blobs; `player/types.ts` is a hand-written mirror with no drift check.**
`api/readerApi.ts:97` (bare type assertion), `player/types.ts:60`
(`schema_version` declared, read nowhere). CI's contract job covers the generated
client types, not the player types, so a v2 schema would play under v1 semantics
silently, eroding the validator's guarantees. **Fix:** check `schema_version` in
`ReaderPage.load()` and route unsupported versions to the error phase; assert the
player enums against `schema/storybook.schema.json` in a test.

**ARCH-M7 (Medium). Server-state fetching is a hand-copied pattern across ~13 pages with no cache.**
Identical `LoadState` + `cancelled`-flag effects in every list page; each new page
is a fresh chance to drop a guard, and there is no caching. **Fix:** extract one
`useLoad<T>` hook (the unions have already converged) or adopt TanStack Query for
the adult consoles only. Related: the generated SDK (`client/sdk.gen.ts`) is dead
weight (types are used, paths are hand-rolled `/v1/` strings), so a backend route
rename compiles clean and 404s at runtime.

**ARCH-L-FE (Low).** `eslint-plugin-jsx-a11y` is absent, so the strong in-code
accessibility work (focus management, `aria-live`, reduced-motion, text-not-color
badges) is not regression-protected; `admin/ReviewDetailPage.tsx` at 1,044 lines
should have its pure blob-parsing extracted; the offline queue orders by
`Date.now()` with a random-UUID tiebreak, allowing a one-step progress regression
on same-millisecond writes.

### Infrastructure

**ARCH-H4 (High). Digest-pinned images have no update automation.**
`renovate.json` `enabledManagers` omits the `dockerfile` and `docker-compose`
managers, so the digest-pinned bases in `Dockerfile`, `frontend/Dockerfile`,
`docker-compose.yml`, and the nginx digest inside `ci.yml` never receive security
bumps; a base-image CVE ships indefinitely, and the `Dockerfile:31` comment
claiming Renovate manages the digest is currently false. **Fix:** add
`"dockerfile"` and `"docker-compose"` to `enabledManagers` plus a regex manager
for the ci.yml digest.

**ARCH-M8 (Medium). The in-repo compose stack cannot run the core pipeline.**
`docker-compose.yml` has Redis entirely commented out and no `worker` service, so
`docker-compose up -d` yields a stack where every generation enqueue fails
silently and jobs sit `queued` forever, contradicting the file's "production-ready
setup" header. Prod runs from a separate homelab repo, so this is a dev/docs gap
that makes the primary feature untestable from this repo. **Fix:** add `redis` +
`worker` services, or relabel the compose stack API-only.

**ARCH-L-INFRA (Low).** `version: '3.9'` is obsolete; the dev DB defaults to
password `password` with the port published to the host (dev-only; prod correctly
requires `DB_PASSWORD`); the `deploy:` blocks in `docker-compose.prod.yml` are
Swarm-only keys and mostly inert under plain `docker compose`, giving a false
sense of resource limits.

### Testing and dependency hygiene

**ARCH-M9 (Medium). The condition evaluator has no recursion-depth bound and no deep-nesting test.**
`storybook/condition.py` bounds integer magnitude but validation/evaluation
recurse unboundedly (the Hypothesis strategy caps at `max_leaves=8`). A deeply
nested condition via the import CLI or a compromised generation stage raises
`RecursionError`: an unhandled 500 on every read/replay of that story rather than
a clean rejection. **Fix:** explicit depth cap in `validate_condition` plus an
adversarial test asserting `ValidationError`.

**ARCH-M10 (Medium). The documented local test loop does not run as written.**
`noxfile.py` sessions install `.[dev]` only, but FastAPI/SQLAlchemy/asyncpg live
in the `api` extra, so `nox -s test` dies at collection; the 3.10 legs violate
`requires-python = ">=3.11"`. CLAUDE.md tells developers to run this as a
pre-push parity check. **Fix:** install `.[dev,api]`, drop the 3.10 legs.

**ARCH-M11 (Medium). The 90% "critical module" coverage thresholds are enforced by nothing, and `api/deps.py` sits outside every strict gate.**
`pyproject.toml:799-814` (`[tool.test-coverage-agent]`) has zero consumers; the
codecov safety-critical component covers `moderation/`, `middleware/`, `core/`
but not the 816-line auth module or `publishing/`. **Fix:** add `api/deps.py` and
`publishing/**` to the codecov safety-critical component, or delete the dead
config table.

**ARCH-L-TEST (Low).** Toolchain skew (pre-commit pins ruff 0.14.6, `uv.lock`
carries 0.15.20, so hooks and CI can disagree); several dead Renovate rules
(pep621 depTypes that the manager never emits, conflicting range strategies);
`--cov-fail-under=80` baked into pytest `addopts` makes the documented
single-test command exit non-zero on a passing test; a stale per-file-ignore for
the removed `utils/financial.py` lingers.

---

## Part 5: Prioritized remediation roadmap

Ordered by impact and grouped so related fixes ship together.

### Tier 1: reliability and child-safety robustness (do first)

- **A1 (ARCH-H1 + ARCH-H2).** Model hard worker death: sweep/reconcile `running`
  jobs after SIGKILL, and make the original enqueue share one RQ identity with a
  status-guarded claim so the reclaim sweep cannot double-execute. These share the
  queue module and should land together. Add an operator surface to clear a
  wedged family cap.
- **A2 (ARCH-H3).** Surface classifier outages as explicit `degraded` findings in
  the moderation report; flip the tests that pin silent fail-open.
- **A3 (ARCH-H4).** Enable Renovate's `dockerfile`/`docker-compose` managers and a
  regex manager for the ci.yml nginx digest.

### Tier 2: kid experience and the core loop

- **A4 (UX-K1).** Cache the library list per profile and give offline kids a real
  door to their downloaded books.
- **A5 (UX-K2).** Ship the text-size control now; put TTS on the roadmap and wire
  or remove the dangling `tts_enabled` field.
- **A6 (UX-G1 + UX-G2).** Give guardians pipeline visibility off the Intake page
  and close the approved-but-unassigned gap (auto-assign to the requester, or make
  the unassigned state loud).
- **A7 (SEC-F1 + SEC-F2).** Fix the kid-route credential fallback: require a
  route-matching child session instead of falling back to the guardian bearer.
  This closes both the offline cross-profile read and the PIN deep-link bypass.

### Tier 3: security hardening and hygiene

- **A8 (SEC-B1 + SEC-B2).** Per-profile PIN attempt lockout plus principal-keyed,
  Redis-backed rate limiting (the device-token threat model makes the PIN a real
  boundary the current IP limiter does not protect).
- **A9 (SEC-F3, SEC-F4, SEC-F5).** Enable PKCE, stop shipping public source maps,
  purge authenticated caches on sign-out.
- **A10 (ARCH-M1, ARCH-M2).** Cover-generation staleness escape hatch and a
  bounded retry policy (or a documented fail-fast + guardian retry action).
- **A11 (docs).** Re-triage the tracked backlog against current code and correct
  the stale status map in `security-hardening-plan-2026-07.md` (C1 and K1 are
  done); fix the CLAUDE.md router count and noxfile MyPy reference via
  `docs/template_feedback.md` per project rules.

### Tier 4: correctness and quality (as capacity allows)

- **A12.** Depth-cap the condition evaluator (ARCH-M9); add `schema_version` gating
  and player-enum drift tests (ARCH-M6); `navigator.locks` around offline replay
  and IndexedDB `blocking` callbacks (ARCH-M4, ARCH-M5).
- **A13.** Fix the nox extras so the documented local loop runs (ARCH-M10); add
  `api/deps.py`/`publishing/**` to the codecov safety-critical gate (ARCH-M11);
  add `eslint-plugin-jsx-a11y` to protect the accessibility work.
- **A14.** UX polish: style `.picker-tile__add-link` (UX-K4), resolve the
  `--color-ink-muted` AA decision (UX-C2), standardize inline retry over "Please
  reload" (UX-C1), admin queue flow-through (UX-A1), 44px floors (UX-K7, UX-A3),
  humanize enum tokens in the approval form (UX-G4).

---

## Strengths worth preserving

So future work does not undo them:

- **Auth boundary** (`api/deps.py`): closed-world role coercion, principal
  invariants at construction, safe unverified-audience routing, same-message
  rejection to avoid probe oracles, import-time guard against the dev auth stub.
- **IDOR closed consistently** at the auth boundary, with a dedicated cross-tenant
  `stranger` fixture sweeping it in tests.
- **Player parity is enforced, not aspirational**: both runtimes execute one
  shared conformance corpus (`schema/conformance/`), with property tests on both
  sides and int/double divergence designed out.
- **Frontend has zero HTML-injection sinks**; LLM prose renders through a
  plain-text component with no markdown path; token redaction is a single choke
  point; 401 classification isolates token families.
- **Supply chain**: SHA-pinned actions, `harden-runner` on every job, no
  `pull_request_target`, distroless non-root runtime, in-process OpenAPI
  contract-drift gate, real-Postgres integration tier with fresh schema per test.
- **Error handling** is centralized and CWE-209-sanitized; the publishing state
  machine is brute-force tested over all illegal transitions.

---

*Prepared by an automated multi-pass review. Every finding cites an exact file
and location; treat the severities as engineering guidance, not a compliance
grade.*
