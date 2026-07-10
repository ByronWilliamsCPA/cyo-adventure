# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- The kid surface no longer collapses every fetch failure into one generic
  retryable error: the profile picker (`/kids`) and library
  (`/library/:profileId`) now distinguish an unauthenticated session (an
  ask-a-grown-up gate linking to guardian sign-in, with no dead-end "Try
  again"), a forbidden response (a way back to the profile picker), transient
  failures (retry, now with an in-page route back to the picker), and the
  existing zero-items empty states. A 401 on a rating save surfaces the same
  gate instead of failing silently, and kid-surface fetch logging is redacted
  to status/url/body so the Authorization header can never reach the console.
  Covered by Vitest state tests and a no-token Playwright scenario in the
  naive-user suite. Fixes #196 and the kid half of naive-UX finding F1 (#137).

### Documentation
- Landed the skeleton corpus story-generation test plan
  (`docs/planning/skeleton-corpus-story-generation-test-plan.md`): a proof-pass
  design for authoring every committed skeleton end to end (prose fill, post-fill
  gate, persist, moderate) rather than only passing the structural gate. Refreshed
  for the current 21-file corpus and for WS-C PR2 (#175) skeleton matching, which
  makes the story-request `skeleton_fill` pipeline a live production path from the
  corpus to the database; inlined the previously memory-only mock-generation
  canned-story hazard (the `MockProvider` "Forest Path" default) and dev-run recipe.
- Landed the naive-user UX test design spec
  (`docs/planning/naive-user-ux-testing-design.md`), the
  design rationale behind the `frontend/e2e/naive-user/*` suite and the
  `naive-ux-check` skill. It documents the two-track methodology (Track A
  Playwright misuse regressions, Track B Claude-for-Chrome comprehension
  prompts) and the B-to-A promotion rule. Added a staleness banner and a
  refreshed Section 4.1 route map reflecting PR #140 (landing page at `/`,
  `/kids` profile picker) and PR #185 (KidNav, reader Leave control, library
  reorder).

### Added
- Generation continuity for series (WS-G PR 3): `AnchorContext` now carries the anchor book's
  declared variable names, and the structure prompt instructs continuations to reuse those exact
  names so a reader's state carries across books; stale ending/metadata guidance in the generation
  prompt templates (`structure.md`, `drafting_guide.md`, `prose.md`) was corrected to the enforced
  schema (`kind`/`valence`, `topology`), including removal of a false "the validator does not
  restrict ending types" claim. Worker-path integration tests now drive `_persist_and_moderate`
  directly, covering the moderation-repair round-trip and the embed-failure rollback (PR #184
  F11).
- Postman/newman API test suite (`docs/api/postman-collection.json`): 75
  requests across 16 resource folders with status, JSON Schema, and
  auth-negative assertions, including the admin authoring-plan happy path and
  the storybook archive lifecycle, run end to end in CI by the `api-tests`
  job against the compose stack (migrated + seeded Postgres, dev-auth mode)
  and reported to Codecov Test Analytics under the `api` flag. The job now
  applies the alembic chain and seeds dev data before newman runs; pacing is
  supplied by newman's `--delay-request` rather than an in-collection
  busy-wait; the suite and its local run loop are documented in
  `docs/api/README.md`.

### Security
- The backend now trusts proxy headers only from an explicit boundary:
  uvicorn's `forwarded_allow_ips` is threaded through Settings, the dev
  docker-compose pins it to the compose network's `172.25.0.0/16`, and prod
  keeps the documented homelab range (follow-up: #138). This repairs both
  rate-limiter keying (previously every client shared the proxy's IP bucket)
  and HSTS emission behind TLS termination, verified by an e2e rate-limit
  keying test behind a real `ProxyHeadersMiddleware`.
- Moderation reviewer and repair prompts now wrap story prose in an
  `<untrusted_passage>` delimiter with instruction-hierarchy framing, and
  literal delimiter tags inside the passage are neutralized, hardening the
  Stage-1/repair pipeline against prompt injection from generated content.
- Resource bounds across the generation surface: request body-size guard and
  reading-state list/dict field caps, `ConceptBrief` node/ending count caps,
  `persist_storybook` blob/report size guards, an Ollama stream-response
  ceiling derived from `max_tokens`, and a per-family active-job throttle on
  `enqueue_concept_generation` (caps derived from real skeleton/cell data).
- CSP tightened with `object-src`, `base-uri`, and `form-action`; correlation,
  request, trace, and span id headers are validated against
  `[A-Za-z0-9_-]{1,64}` and never echoed back when invalid (CRLF and oversize
  covered by tests); the SSRF guard docstring now matches what the code
  actually checks.
- Concept intake strips control characters (closes #64, safety-eval Finding 5),
  and publishing hard-blocks submitting a story version that has not passed
  moderation screening, mirroring the existing `approve()` check (closes #57).

### Added
- Series continuation runtime (WS-G PR 2): kid-scoped `GET /api/v1/series-next` endpoint,
  "Continue the series" on satisfying endings of non-final series books with entry-node jump
  and name-matched variable-state seeding for state-carrying series, regenerated API client,
  and chained-reading e2e coverage in both Playwright tiers.
- Admin-generated story book covers: from a published story version an admin
  can trigger cover generation, which builds a textless-art prompt from the
  story content, calls Gemini image generation ("nano banana" Pro) in an async
  worker, optimizes the result to a small WebP within the 500MB Supabase
  Storage budget, uploads it to a public `covers` bucket, and renders a portrait
  cover on the kid library's `BookCard` (with a first-letter tile fallback). New
  `cover_image_url` + `cover_status` columns on `StorybookVersion`, admin-only
  cover endpoints, and `cover_url` on `LibraryItem`.
- Story requests carry `initiator_role`, `age_band`, `length`, and
  `narrative_style`; guardians confirm band and length at approval (the
  approve endpoint now requires them), and generation reads them from the
  request instead of the child profile (WS-B PR 1).
- Guardians and admins can now create a story request directly in
  `approved` status via `POST /api/v1/story-requests/authored`, skipping the
  guardian-approval step; the request still goes through moderation
  screening and can be blocked by it. The endpoint is role-gated (child
  tokens get a 403) and admin-authored requests require a family
  (`family_id` is forbidden for guardians, required for admins; `profile_id`
  is optional for both roles). A new
  `GET /api/v1/admin/families` endpoint lists families (id and name only)
  to back the admin family selector. `StoryRequestView.profile_id` is now
  nullable to represent authored requests with no linked child profile. The
  request-a-story page gained a guardian variant (optional child selector,
  band/length/style at creation) and the admin console gained an admin
  variant (required family selector) of `RequestStoryForm` (WS-B PR 2).
- Age-band moderation thresholds: the moderation pipeline now records every
  advisory finding, and a per-`(age_band, category)` threshold determines
  which findings surface on the two guardian-facing surfaces: the story
  content summary and the story-request list. Findings below the configured
  floor for a story's age band are recorded for audit but filtered out at the
  serialization boundary; admins continue to see every finding on both
  surfaces regardless of this per-age-band threshold; a separate, admin-only
  noise floor on the admin review surface itself is described below and does
  not affect this guarantee. A new admin CRUD editor
  (`/guardian/moderation-thresholds`) lets admins view and adjust thresholds
  per age band and category, with every change written to an audit trail.
  That same editor now also exposes an admin-configurable global moderation
  noise floor: ADVISORY findings scoring below the floor are hidden from the
  admin review surface, while FLAG and BLOCK findings (and unscored findings)
  always surface, so a genuine low-but-real score is not buried in a wall of
  near-zero advisories.
- Landing page at `/` with two doors: Kids (to the profile picker, now at
  `/kids`) and Grown-ups (to the guardian console; admins sign in there too).
  Kid deep links (`/library/...`, `/read/...`) are unchanged; the reader's
  "Back to start" fallback now returns to `/kids`.
- Kid profile picker now recovers from a failed load instead of dead-ending: the
  error state is a `role=alert` live region with a Retry button and a "grown-up"
  sign-in link (naive-UX K1, #73).
- Guardian console and intake nudge a childless family toward profile creation:
  the console empty state and the intake "Add a child profile first" hint are now
  real links to `/guardian/profiles` (naive-UX F3/F4).
- Reading-level-cap field explains that 99 means no limit via `aria-describedby`
  (naive-UX F5).
- Shared `classifyApiError` helper distinguishes 401 / 403 / transient failures so
  a permanent permission error (for example an admin creating a child profile) no
  longer reads as a retryable "try again" (naive-UX F1, G2).
- Series tagging and soft continuation for story requests: kids can propose a
  series title or continue an existing story from the library, guardians ratify
  or edit the series title (or clear it) at approval, guardians and admins can
  create an authored request directly in a series via anchor storybook id, and
  book numbering within a series is assigned race-safely at generation
  completion rather than at request time (WS-B PR 3). A DB check constraint
  enforces that an anchored (continuation) request always carries its series
  id, the approve path re-syncs that id from the resolved anchor, and the
  book_index retry loop only retries the genuine unique-index conflict
  (WS-B PR 3 review hardening).
- A DB-backed, admin-editable provider/model allowlist with a full audit
  trail (`/api/v1/admin/provider-allowlist`); a direct-Anthropic generation
  provider via the official SDK (canonical name `anthropic`, replacing the
  dead `claude` literal); `build_provider()` is now a per-job factory so an
  admin's chosen provider/model on the authoring-plan step overrides the
  global default (WS-C PR 1).
- Append-only `pipeline_event` log capturing every story-lifecycle transition
  (request, plan, generation, moderation, release, threshold, assignment, rating),
  the capture layer for the learning loop (WS-D).
- Admin moderation suggestion dashboard (WS-F): override evidence per
  (age band, category) aggregated from persisted moderation reports and the
  pipeline event log, computed threshold suggestions behind volume and rate
  gates, and an apply control that ratifies a suggestion through the existing
  audited threshold upsert. Two new admin-only GET endpoints under
  `/api/v1/admin/moderation/`; no migration, no new event type, no
  auto-calibration.
- Cell-aware skeleton matching for skeleton-fill authoring plans (WS-C PR 2): selection now
  matches the full ADR-011 `(age band, length, narrative style)` cell instead of band-only,
  weights the pick against the family's recently-used skeletons with a nonzero floor, and lets
  an admin override to any skeleton on disk (with a non-blocking warning on a non-production or
  out-of-cell pick). `AuthoringPlanResponse` now returns every in-cell alternative, and
  `storybook_version.skeleton_slug` records which skeleton produced each version.
  The admin override slug is charset- and length-bounded at the request boundary
  (`^[a-z0-9][a-z0-9-]*$`, max 120), and every skeleton-fill path resolves the on-disk
  file through a shared containment check that rejects any band or slug escaping the
  skeleton root, so an untrusted override cannot traverse the filesystem. An override
  now resolves before the empty-cell guard, so a cross-cell override succeeds even when
  the request's own cell has no eligible skeleton; unreadable, schema-invalid, and
  band-ambiguous skeletons are logged and surfaced as distinct errors rather than
  silently treated as absent.
- Series chaining (WS-G PR 1): generated series books embed their document
  `Series` metadata block; SR-4 accepts open-ended chains; release approval
  validates the chain-so-far and blocks on SR errors (legacy pre-WS-G chains
  are grandfathered).
- Story catalog: at release approval an admin now chooses whether a book stays
  family-only or joins the shared catalog (`visibility` on `Storybook`). Guardian
  browse lists catalog books from every family with a "Catalog" badge, and
  assignment enforces visibility server-side: any guardian may assign a catalog
  book, while another family's private book stays 403. Assignment sets returned
  to a guardian are always scoped to their own family's children. Children can
  read and rate an assigned catalog book from another family; unassigned
  catalog books stay hidden from child accounts. Admin-initiated catalog-origin
  requests are deferred (#173).
- Kid-friendly navigation and character-led redesign of the kid surface: a
  persistent `KidNav` wayfinding bar (whose books these are, plus a Switch
  reader control), a Leave control in the reader, a books-first library
  layout, Pip the fox mascot at the moments a child might feel lost or
  triumphant, painted first-letter cover fallbacks for books without cover
  art, and refreshed kid-surface design tokens.

### Changed
- Test suites audited against the org testing standards and hardened to a
  granular 70% per-file/function/class/branch coverage floor (aggregates were
  already 95%+ but masked 5 backend files, 47 functions, and 8 frontend files
  below floor; all closed, critical moderation modules now 100%). New
  role x endpoint x method authorization matrix (46 endpoints, exact status
  codes, completeness-gated), logging-security tests (malformed bearer tokens
  and DSN passwords kept out of auth and engine-configuration log paths),
  Vitest per-file 70% thresholds, `filterwarnings = ["error"]` with
  `xfail_strict`, pytest-mock installed for future adoption (tests still use
  `unittest.mock`), mock `spec=` discipline adopted, and
  the moderation-pipeline unit tests de-mocked to run real stages through
  boundary seams (raising pipeline branch coverage 88% -> 93%). Full audit
  report in `docs/planning/test-coverage-audit-2026-07-09.md`.
- Removed the unwired `.semgrep.yml` config: it was never invoked from
  `.pre-commit-config.yaml` or any `.github/workflows/` job, so it added no
  scanning coverage. The active SAST/SCA gates remain Bandit, OSV-Scanner,
  CodeQL, and SonarCloud (refs #61).
- Frontend ESLint is now type-aware (`tseslint.configs.recommendedTypeChecked`
  with `projectService`), and lint coverage now extends to `e2e/` and
  `e2e-real/`, previously outside the lint glob entirely. This is the class of
  rule (`@typescript-eslint/no-floating-promises`) that would have caught
  issue #110's dropped-promise bug, where a replay was enqueued but the
  promise handling it was never awaited or observed. A new
  `frontend/tsconfig.e2e.json` type-covers the Playwright specs (added to the
  `tsconfig.json` project references), and around 70 newly-surfaced
  violations (floating promises, unsafe `any` member access/return, unsafe
  promise rejection reasons, an unbound-method false positive, and a couple of
  redundant type assertions) are fixed with no rule weakened or suppressed.
- `run_generation_job` (`generation/worker.py`) is refactored into three
  focused helpers (`_load_and_start_job`, `_load_concept_and_pii`,
  `_persist_passed_outcome`) alongside the existing `_record_failure`, with no
  behavior change: the same failure-recording, completion-flag, and
  finally-guard semantics from the D/D3 remediation are preserved exactly.
  Closes F17.
- The frontend's hand-typed `MeResponseBody` (`auth/AuthContext.tsx`) and
  `ConflictBody` (`api/readerApi.ts`) shadow interfaces are replaced with
  aliases of the generated OpenAPI client's `MeResponse`/`ConflictView`
  types, so a backend contract change surfaces as a type error instead of a
  silent shape drift. Full `sdk.gen` adoption (routing every hand-rolled axios
  call through the generated client functions) is left to a follow-up PR.
  Closes F7 (minimum-viable slice).
- Removed the unused `components/ApiStatus.tsx` scaffold (plus its CSS) and
  the unreferenced `apiClient` standalone axios export from `hooks/useApi.ts`;
  neither had any remaining import. Closes F22.

### Fixed
- Codecov configuration was silently invalid (a `testcase` comment-layout
  token, a misplaced `flag_coverage_not_uploaded_behavior`, and a `behavior`
  field on individual flags), which made Codecov discard the whole file and
  fall back to defaults, ignoring every declared flag and component. The file
  now passes `codecov.io/validate`. Flags are now test-type on the backend
  (`unit`, `integration`, `security`, each uploaded from its own
  `coverage-<type>.xml`) and surface on the frontend (`frontend`,
  `design-system`, which cannot split by type), plus a dormant `api` Test
  Analytics flag; the code-area split moved to components, including
  safety-critical (moderation + security + core, 90/95) and generation-pipeline
  (85/90).
- Backend coverage now uploads to Codecov from an inline `coverage-upload` CI
  job (per test type) instead of a `main`-only `workflow_run` workflow, so
  backend coverage and patch coverage are visible on pull requests for the
  first time; the redundant `.github/workflows/codecov.yml` was removed.
- The `coverage-upload` job now checks out the repository before uploading.
  pytest-cov emits two `<source>` roots (`src` and `src/cyo_adventure`), which
  Codecov disambiguates against the git file tree; without a checkout every
  report was rejected server-side as "source code unavailability / path
  mismatch", so the first main run after the config fix showed 0% with ten
  upload errors despite healthy 91%+ reports in the artifact.
- Frontend and design-system coverage now reach Codecov and aggregate with the
  backend into one commit total. Two fixes were needed: (1) an explicit
  `coverage.include: ['src/**']` in both Vitest configs, since without it the v8
  provider reported every file the run touched (`node_modules`, `dist`, e2e
  specs, paths above the package root); and (2) rewriting the lcov `SF:` paths
  to be repo-root-relative (`frontend/src/...`,
  `frontend/design-system/src/...`) before upload, because Vitest emits them
  relative to the package root and Codecov matches against the repo tree. Until
  both were in place the reports uploaded but were dropped server-side as "path
  mismatch", so only the backend sessions merged and the `frontend` /
  `design-system` flags stayed empty.
- Qlty Cloud coverage now publishes from the CI jobs that hold the checkout
  (`coverage-upload` for the backend Cobertura reports, and the `frontend` /
  `design-system` jobs for their prefixed lcov) instead of the `workflow_run`
  `qlty.yml`, which was removed. `qlty coverage publish` needs the repository
  checked out to resolve the Cobertura `<source>` roots and to read the commit
  SHA from git; the reusable `workflow_run` caller had neither, so its uploads
  carried unresolvable paths and no commit association and never surfaced on the
  Qlty dashboard (the job stayed green). qlty merges the per-surface uploads
  into one coverage number for the commit, mirroring the Codecov sessions.
- The Qlty upload steps are now `continue-on-error`, so a transient Qlty upload
  failure cannot fail the `frontend` / `design-system` / `coverage-upload` jobs
  and block an unrelated merge, matching the Codecov steps' `fail_ci_if_error:
  false`.
- The integration and security test buckets now run in CI
  (`run-integration-tests` / `run-security-tests`); previously the reusable
  workflow's unit step excluded `-m integration`/`-m security`, so those
  test files never executed in CI.
- OpenAI Moderation's `_run_openai` now logs `openai_moderation_malformed`
  when the response's `categories` field degrades to an empty map (missing or
  non-dict shape), matching the sibling shape-check log lines instead of
  failing silently. Closes F15.
- `StorybookVersion` now records a `provider` column (nullable, added by
  migration `a7b8c9d0e1f2`), stamped by the generation worker at persist time
  and by the offline authoring import path (sentinel `"import"`), so a
  version's provenance is queryable independently of the owning job's
  `provider` field. Closes #63/F18.
- The `worker_main` reclaim sweep no longer poisons the shared async engine
  pool: the sweep now disposes the engine's connection pool inside its own
  event loop before `Worker.work()` starts, so pooled asyncpg connections
  bound to the sweep's closed loop can no longer crash the first generation
  job (or any forked RQ work horse) with a cross-loop
  "got Future attached to a different loop" RuntimeError. Closes #150.
- Concurrent approvals of the same story can no longer double-apply state
  transitions: `api/approval.py` and `moderation/pipeline.py` load the story
  row with `SELECT ... FOR UPDATE` so a second approve/submit blocks on the
  first transaction instead of racing it. Closes #129.
- Generation jobs can no longer be silently stranded: jobs run under an RQ
  `job_timeout`, every failure path records a `failed` status through one
  shared helper, a top-level guard force-fails a job interrupted mid-run
  (tracking completion with an explicit flag set only after the terminal
  commit, so an interrupt landing after an in-memory status write but before
  the commit still records `failed`, not a phantom `passed`), and a reclaim
  sweeper (`requeue_stranded_jobs`, run by the new `worker_main` entrypoint)
  re-enqueues rows whose worker died before ever starting. Requeue is
  idempotent via RQ-native unique job ids, so overlapping sweeps cannot
  double-enqueue. Verified against a real Redis testcontainer.
- Unexpected response-shape errors (`ResponseValidationError`) now return the
  standard error envelope instead of an unhandled 500 traceback. Closes #48.
- Offline reading progress queued while disconnected is now actually sent to
  the server: the replay queue flushes on reader mount and on the browser
  `online` event (previously nothing ever called `replayQueue`, so queued
  writes sat in IndexedDB forever). Replay conflicts surface a keep-this-device
  / use-newest dialog; keep-this-device rebases and retries once on a second
  conflict instead of silently dropping progress, and outright resend failures
  land in a dismissible failed-progress banner. Same-device save-then-reload
  resume is covered by a new e2e spec. Closes #110 and #62.
- Story generation now recovers from Stage 1 fidelity violations instead of
  failing the job outright: the fidelity gate is folded into the skeleton-fill
  repair loop, sharing the single `max_repairs` budget with structural repairs
  and using a dedicated fidelity repair prompt that rewrites the flagged node
  body while freezing the story structure. The previous worker-level outer
  retry loop (blind full-pipeline retries on a separate budget) is removed.
  Closes #133.
- The Stage 1 review model now defaults to the job's `prep_model` instead of a
  hard-coded default, threaded from `GenerationJob.model`. Closes #134.
- `resume_manual_fill` loads the skeleton before persisting anything, with a
  downgrade-to-`needs_review` safety net if the skeleton file is missing, so a
  deleted skeleton can no longer strand a half-persisted story. Covered by a
  real file-deletion integration test. Closes #128.
- The integration test suite now fails instead of silently skipping when
  Docker/testcontainers is unavailable while running in CI (`CI` env var set
  to a truthy value such as GitHub Actions' `CI=true`); local runs without
  Docker, including an explicit `CI=false`, still skip as before. Previously a
  broken CI runner's testcontainers setup would show green by skipping the
  entire suite.
- Stage-0 classifier findings now apply an advisory noise floor (score >=
  0.01): OpenAI Moderation and Perspective return a nonzero score for every
  category on every call, so every clean node previously emitted all 13
  OpenAI categories as advisory findings (11 nodes x 13 = 143 findings on the
  first live story, max real score 0.0006) and the admin review surface read
  as "every section flagged with every flag". Sub-floor scores are dropped;
  OpenAI provider-flagged categories and bright-line blocks bypass the floor.
  Advisories never gate (`has_soft_flag` counts `FLAG` only), so approval
  outcomes are unchanged; this also shrinks the ~70KB per-version
  `moderation_report` accordingly.
- The browser tab title and meta description now render real values ("CYO
  Adventure" / the app description) instead of the literal unrendered
  `{{ cookiecutter.project_name }}` placeholders in `frontend/index.html`;
  surfaced by a naive-user UX pass where the placeholder was the first thing a
  kid persona noticed. Takes effect on the next frontend image rebuild.
- Guardian review actions are gated on story status: Approve and Send Back are
  disabled (with an `aria-describedby` hint explaining why, and their action names
  preserved for assistive tech) for a story that is not `in_review`, closing the
  re-approval affordance gap (#130).
- Guardian surfaces redirect to the login page on a 401 (token cleared via
  `window.location.replace` so the expired URL does not linger in history); kid
  surfaces keep their own picker recovery (#73).
- Guardian Google sign-in now completes in the browser: `signInWithOAuth` passes
  `redirectTo=<origin>/guardian/login` so the OAuth callback returns to the
  guardian subtree. Previously it returned to Supabase's Site URL (`/`, the kid
  surface), which never imports `@supabase/supabase-js`; the callback hash was
  never processed, the session was never persisted, and the token bridge that
  writes `auth_token` never ran, so the guardian landed unauthenticated and
  every API call went out tokenless ("We could not load your profiles"). Requires
  `<origin>/guardian/login` in the Supabase Auth redirect allowlist.
- Removed a duplicated `ARG`/`ENV` block for `VITE_SUPABASE_URL` and
  `VITE_SUPABASE_ANON_KEY` in the frontend Dockerfile builder stage (added by
  #117 under the mistaken belief the args were undeclared; #103 had already
  declared them, and published images since #103 carry the Supabase config).
  The duplicate was functionally harmless (both defaults are empty and the
  later declaration wins) but its comment misdescribed the deployed state. The
  "We could not load your profiles" symptom that prompted #117 was the guardian
  OAuth callback landing on the signed-out kid-surface profile picker (which has
  no sign-in affordance); that redirect is the entry above, fixed by returning
  the callback to /guardian/login.
- The production backend image now actually starts: the venv is created against
  the hardened runtime image's `/opt/python` interpreter path (previously every
  console script exec-failed on a dangling symlink), the `api` extra
  (fastapi/uvicorn/alembic/sqlalchemy/asyncpg) is installed into the image
  (previously the web framework and migration runner were missing entirely),
  the CMD targets the real application module `cyo_adventure.app:app` (there is
  no `main.py`), and `jsonschema` is declared as a main dependency instead of
  arriving transitively via dev tooling. Found on the first live docker-host
  deploy: the worker crash-looped with `exec /app/.venv/bin/rq: no such file
  or directory`.

### Added
- `contract` CI job (`.github/workflows/ci.yml`): dumps the FastAPI app's
  OpenAPI schema in-process, regenerates the frontend API client against it,
  and fails the build on any diff, so a route or model change that was not
  followed by `npm run generate-client` no longer merges unnoticed. Required
  the generated client at `frontend/src/client/` to actually be tracked in
  git (it was gitignored with no CI step ever regenerating it); it is now
  committed as build output. Added to the `ci-gate` required job list.
- `pytest.mark.security` now actually tags tests (OIDC/JWT verification,
  IDOR/authorization, and the security-middleware suite), so the org reusable
  CI workflow's `pytest -m security` step collects real tests instead of
  silently running zero.
- Naive-user UX test suite: Playwright misuse regressions for kid, guardian,
  and admin personas (`frontend/e2e/naive-user/`, `frontend/e2e-real/`), a
  Claude-for-Chrome comprehension prompt set, and the `/naive-ux-check` skill.
- Authoring-path routing for approved story requests: a new admin-only
  `POST /story-requests/{id}/authoring-plan` endpoint lets an admin choose how a
  request is authored via `method` (`skeleton_fill` or `fresh_generation`) and
  `mechanism` (`skill` or `automated_provider`), plus a `prep_model` and optional
  `review_stage1_model`/`review_stage2_model` overrides. The illegal
  `fresh_generation` + `skill` pairing is rejected at the schema boundary (422).
  The `automated_provider` + `skeleton_fill` path runs a new Stage B' fill
  pipeline (`fill_skeleton`, reusing the existing repair loop) followed by a
  Stage 1 fidelity gate (pure-code structural checks plus one semantic
  reviewer call); a clean fill that a Stage 1 check downgrades is still persisted
  and moderated so an admin can review a real story instead of an empty job row.
  The `skill` + `skeleton_fill` path parks the job at `awaiting_manual_fill` for
  a human to fill via the `cyo-author` skill and resume through
  `generation/import_cli.py --job`.
- `CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE` setting (default `false`) that
  disables both asyncpg's own prepared-statement cache and the SQLAlchemy asyncpg
  dialect's separate cache, gives each prepared statement a unique name, and
  switches the engine to `NullPool` so no connection (and therefore no server-side
  prepared statement) is reused across logical checkouts. Set it to `true` when
  `CYO_ADVENTURE_DATABASE_URL` points at a transaction-mode connection pooler
  (Supabase Supavisor on `:6543`, or PgBouncer transaction mode), where a cached or
  fixed-name server-side prepared statement collides when the pooler reassigns a
  backend mid-session and 500s requests under concurrency. A `model_validator`
  fails fast at startup if `CYO_ADVENTURE_DATABASE_URL` uses the Supavisor `:6543`
  port with this flag left `false`. This is the backend enabler for the ADR-009
  Task 1.7 cutover to Supabase Postgres; a direct connection (local dev, or the
  Supabase `:5432` DSN used by Alembic) leaves it `false` and keeps server-side
  prepared statements under the default `QueuePool`.
- Guardian console, sign-in, intake, profiles, and reader 409-conflict flows now
  have Playwright e2e coverage (all seven amber gaps from the journey coverage
  map), plus a real-backend smoke tier exercising the ADR-005 approve path
  against FastAPI + Postgres. The mocked tier runs in CI on every PR; the
  real-backend tier is local-only (run per `frontend/README.md` before opening
  a PR) because it needs Postgres and a seeded uvicorn.
- Child story-request endpoints: `POST /api/v1/story-requests` (a kid's free-text
  idea, guardian-scoped in R1, screened for PII and Stage-0 classifier hits before
  landing as `pending` or `blocked`, capped at 5 pending requests per profile),
  `GET /api/v1/story-requests` (family-scoped list for a guardian, global for an
  admin, filterable by status/profile), and `POST /{id}/approve` /
  `POST /{id}/decline` (guardian own-family or admin global; a request outside the
  caller's scope returns 404, existence hiding, diverging by design from the
  generation API's cross-family 403). Approval builds a `ConceptBrief` from the
  stored request text and enqueues generation the same way as a guardian-authored
  concept, reusing the generation pipeline without a separate approval-specific
  code path. A guardian review UI at `/guardian/requests` (nav-linked as
  "Story requests") lists the pending queue with redacted moderation flags,
  offering per-row Approve/Decline actions guarded against duplicate clicks
  and surfacing a visible notice on failure. A kid-facing "Request a story"
  affordance on the library page (`/library/:profileId`) lets a child open a
  short idea box, send it, and see their own requests in friendly,
  age-appropriate language ("Waiting for a grown-up to say yes", and a
  distinct "Let's try a different idea!" message when the pending cap is
  hit); no moderation detail, family scoping, or other guardian-facing field
  ever reaches the kid surface.
- Guardian and admin content review summary: `GET /api/v1/storybooks/{id}/content-summary`
  returns a redacted moderation summary (screened flag, gating summary, flagged
  count, story-level findings only), rendered as content tags in the guardian
  assign dialog. Per-node flagged passages remain admin-only.
- Guardian browse-and-assign books page: `GET /api/v1/guardian/books` lists every
  published, approved book in the caller's own family (not just their own request
  history), each with a redacted content badge (screened flag + flagged count,
  reusing the Task 2.1 projector with per-row corruption isolation) and the set of
  child profiles it is assigned to. The new `/guardian/books` page (guardian-only
  nav entry) reuses `AssignChildrenDialog`, which continues to lazy-fetch the full
  content tags from the content-summary endpoint on open. The list endpoint is
  guardian-only: a child or an admin receives 403 and the page shows a clear
  notice.
- Experimental `ModalProvider` generation leg (ADR-010 item 2): an HTTP adapter
  mirroring `OpenRouterProvider` for self-hosted generation via Modal Auto
  Endpoints, wired behind `generation_provider=modal` as a bare leg that never
  enters the production `FallbackProvider` cascade. Includes a `--provider
  modal` choice for `scripts/yield_harness.py` and an operator runbook
  (`docs/guides/modal-endpoint-deployment.md`). Proxy-token auth uses the
  `Modal-Key`/`Modal-Secret` header pair (confirmed against Modal's actual
  Auto Endpoint auth mechanism during a live deployment, correcting an
  initial Bearer-token assumption). Verified end to end against one live
  Modal Auto Endpoint (Standard tier, `google/gemma-4-26B-A4B-it`): 1/1
  story passed all gates, 100% pass rate, 25.5s latency (result recorded at
  `docs/planning/yield-results/modal-standard-smoke-test.json`); the
  endpoint was stopped immediately after to halt billing. This is one
  measured data point toward the ADR-010 promotion gate, not the gate
  itself; OpenRouter (Claude) remains the generation primary.
- Gamebook production skeletons (Batch 5), one per gamebook cell of the ADR-011 matrix, all
  `branch_and_bottleneck`: `13-16 medium` (The Sunspire Ascent, 252 nodes, 74 endings),
  `16+ medium` (The Drowned Court, 314 nodes, 105 endings), `13-16 long` (The Thornwood Trial,
  375 nodes, 115 endings), and `16+ long` (The Ashfall Expedition, 505 nodes, 143 endings).
  Gamebooks use terse sections and the 0.25 breadth floor, so each fans out into many short
  non-lethal `setback` endings off a long spine of hub nodes, with a handful of winning arcs
  earned deep (shortest satisfying paths 26/30/35/48 nodes, each above its cell floor). Every
  cell is scale-classified and clears the full PL-17/19/20/21 gate. **This completes the launch
  corpus: all 18 offered cells of the ADR-011 band x length x style matrix now have at least one
  production-eligible skeleton.**
- Long-prose production skeletons (Batch 4), one per long-length prose cell of the ADR-011
  matrix, all `branch_and_bottleneck`: `8-11 long` (The Clockwork Menagerie, 166 nodes,
  27 endings), `10-13 long` (The Mapmaker's Island, 224 nodes, 72 endings), `13-16 long`
  (The Vanishing Orchard, 177 nodes, 33 endings), and `16+ long` (The Salt Archive, 225
  nodes, 54 endings). Each is scale-classified (`length` + `narrative_style` +
  `production_eligible: true`) and clears the full PL-17/19/20/21 gate, with every satisfying
  arc earned above the cell floor (28/18/43/43 nodes) and every failure outcome a non-lethal
  `setback`. Node counts sit near the low end of each cell budget so the breadth-scaled PL-17
  floors stay proportionate. This brings the launch corpus to 14 of the 18 offered cells; only
  the four gamebook cells remain.
- Medium-prose production skeletons (Batch 3), one per remaining medium-length prose cell of
  the ADR-011 matrix, all `branch_and_bottleneck`: `8-11 medium` (The Sky-Ship Stowaway,
  111 nodes, 20 endings), `10-13 medium` (The Hollow Lighthouse, 148 nodes, 31 endings),
  `13-16 medium` (The Signal in the Static, 123 nodes, 32 endings), and `16+ medium`
  (The Last Train North, 143 nodes, 25 endings). Each is scale-classified
  (`length` + `narrative_style` + `production_eligible: true`), clears the full
  PL-17/19/20/21 gate with its fastest satisfying arc above the cell floor, keeps every
  failure outcome a non-lethal `setback`, and is auto-discovered by
  `test_production_skeletons_*` and rendered into the catalog. This brings the launch corpus
  to 10 of the 18 offered cells.
- Three more production-eligible story skeletons (Batch 2), completing the small-prose
  corner of the ADR-011 matrix: `3-5 short prose` (Clover and the Butterfly, time_cave,
  20 nodes), `3-5 medium prose` (The Teddy Bears' Picnic, loop_and_grow, 29 nodes), and
  `5-8 medium prose` (The Backyard Treasure Map, time_cave, 61 nodes). Each declares
  `length` + `narrative_style` + `production_eligible: true`, passes the full
  PL-17/19/20/21 gate (`blocked=False`), and is discovered automatically by the
  glob-based `test_production_skeletons_*` pin test.
- Guardian email/password sign-in on the login page, alongside the Google OAuth button
  (ADR-009). The form calls `supabase.auth.signInWithPassword`, which
  establishes the same Supabase session the OAuth path produces, so the `AuthProvider`
  resolves the backend `Principal` via `/me` unchanged, no new auth machinery. A new
  `signInWithPassword` context method rethrows Supabase's `{ error }` (matching
  `signInWithOAuth`), and the form surfaces one generic "email and password didn't match"
  message that never reveals whether an email is registered. This unblocks the R1 family
  logins provisioned directly in Supabase, which previously had no browser entry point
  (the page was OAuth-only). Covered by `LoginPage.test.tsx` (submit, failure message,
  signed-in redirect) and new `AuthContext` delegation/rejection tests.
- First production-eligible story skeletons (P1), one per launch cell of the ADR-011
  matrix: `8-11 short prose` (The Cave of Echoes, time_cave, 64 nodes),
  `5-8 short prose` (The Lantern Festival, loop_and_grow, 36 nodes), and
  `10-13 short prose` (The Midnight Museum, branch_and_bottleneck, 94 nodes). Each
  declares `length` + `narrative_style` + `production_eligible: true`, so it is
  scale-classified and passes the full PL-17/19/20/21 gate; each is pinned
  `blocked=False` by `test_production_skeletons_*` and rendered into the catalog. ADR-011
  section 7 gains a per-band topology and flow-allowance table (folded from the retired
  expansion-plan doc).
- Reader storybook styling and error-state redesign: the reader (the last kid surface without
  the design system) now composes from the shared PR #44 components (`PassageText`,
  `ChoiceButton`, `StatusBadge`, `ProgressBar`, `EmptyState`, `Button`) with a centered
  parchment reading column and a slim persistent status/progress top bar. The reader's single
  catch-all error path becomes a typed phase machine (`loading`/`reading`/`not-found`/
  `offline`/`error`): a missing story (`404`) shows an honest "We couldn't find that story"
  screen instead of the offline "save space" copy, a genuinely offline device shows the
  download screen, and every non-reading screen (not-found, offline, error, both `ReaderRoute`
  bad-URL guards, and the ending) now has a working "Back to my books" exit rather than a dead
  end. `makeFetchStory` gains typed failures (`StoryNotFoundError`/`OfflineError`), and a
  non-conflict save rejection in `persist()` is caught and logged instead of becoming an
  unhandled promise rejection. Adds Playwright coverage for the exits, the not-found screen,
  no horizontal scroll at 390px, and 44px choice tap targets.
- Story-scale (P0) enabler implementing the ADR-011 band x length x style framework as
  additive, opt-in validator and generation changes (no existing fixture or seed declares a
  `length`, so the corpus is unaffected). A non-production MVP/Test tier
  (`metadata.production_eligible`) budgets prototyping skeletons against a band-independent
  node envelope; per-cell production budgets (`band_profile._PRODUCTION_CELLS`) lift the
  band ceiling for a scale-classified story via a shared `layer1.resolve_node_budget` that
  both the L1-7 gate and the Stage A prompt read, so the prompt promises exactly what the
  gate enforces. New policy rules extend the gate to PL-21: PL-19 (per-node word wall guard
  plus a scale-classified story-mean advisory), PL-20 (fastest-finish arc floor so a hollow
  quick win blocks), breadth-scaled PL-17 ending/decision floors, and PL-21 (reject an
  off-matrix `(band, length, style)` such as a 3-5 long instead of silently downgrading).
  The `Topology` enum gains `open_map` and `sorting_hat` with classifier support; a `Series`
  model plus a cross-book `validator.series` meta-validator (rules SR-1..SR-7) encode the
  ADR-011 campaign-continuity invariant; and `band_profile.offered_cells` exposes the
  coverage grid. `ConceptBrief` gains optional `length` and `narrative_style` so generation
  can request a scale cell.
- Guardian concept-intake UI (C4a-5): a "Request a story" form that picks a
  child, captures a premise and tone, builds a full ConceptBrief from
  band-derived defaults, posts the concept, and enqueues generation. A
  persistent "My Requests" list polls while a request is generating and shows a
  status pill (Generating / Waiting for review / Approved / Failed) per request.
- `GET /api/v1/generation-jobs`: a guardian-only, family-scoped endpoint that
  lists a family's generation jobs newest-first with the linked storybook
  status, and never returns the raw generation report (ADR-007).
- Assign-to-profile (C4a-6): a `storybook_assignment` table and a guardian-only
  assign API (`POST`/`GET /api/v1/storybooks/{id}/assignments`) that becomes the
  read-gate for a child's library. `list_library` and the direct version fetch
  now require an assignment row for the child's profile, so a child sees only
  stories explicitly assigned to them. An Alembic migration backfills one row per
  (child, published story) per family, preserving prior visibility. Frontend adds
  a guardian `AssignChildrenDialog` multi-select and `makeAssignApi` adapter,
  wired into the intake page's approved-request rows via an "Assign more" action.

### Fixed
- Reader progress correctness (three findings, one slice): the reader now posts
  `POST /api/v1/completions` once when a story reaches an ending (idempotent via a
  per-ending client guard plus the server's primary-key dedup); a cleared-cache or
  new device resumes from `GET /api/v1/reading-state/{profile}/{storybook}` when
  the local IndexedDB cache is cold, with local state still winning when present;
  and the React StrictMode double-invoke of the initial save is deduped by a
  content signature so opening a story no longer issues a duplicate write or
  surfaces a false "reading on another device" 409 (issue #86).
- Fixed `frontend/Dockerfile` failing to build against the hardened
  `dhi-node`/`dhi-nginx` GHCR mirror images used for the homelab R1 deploy.
  Both runtime tags ship no shell, which broke every shell-form `RUN` (`npm
  ci`, `npm run build`, `apt-get`/`groupadd`/`useradd`). The `deps`/`builder`/
  `development` stages now build from the new `dhi-node:22-debian13-dev`
  builder variant; the `production` stage reuses `dhi-nginx`'s own built-in
  non-root user (uid/gid 65532) instead of creating one, sets ownership via
  `COPY --chown`, drops the `curl`-based `HEALTHCHECK` (no HTTP client
  available to run one with), and fixes `CMD` duplicating the binary name
  against the base image's own `ENTRYPOINT ["nginx"]`.
- Enabled the `/api` reverse-proxy block in `frontend/nginx.conf`, needed for the
  homelab R1 internal-web deploy where nginx is the ingress point in front of the
  FastAPI container. Also added a `backend` network alias on this repo's own `app`
  compose service, deferred the proxy's upstream DNS resolution to request time
  (so nginx no longer fails to start if the backend container isn't already up),
  tightened the location match to `/api/`, and set explicit proxy timeouts and a
  request body size limit.

### Security
- Closed the moderation-bypass seams recorded as C3-SAFETY Findings 1-3 in the
  adversarial safety evaluation: `generation/import_story.py::import_filled_story`
  now runs the moderation pipeline before returning, so the import path can no
  longer reach `in_review` unscreened; `publishing/service.py::approve`
  structurally refuses to publish any version whose `moderation_report is None`,
  raising `BusinessLogicError`; and `ReviewSurfaceView` gains an explicit
  `screened: bool` field (`build_review_surface`) so a never-screened draft can
  no longer be mistaken for one screened clean. The credentialed
  live-adversarial-harness run (Finding remainder (c)) is still blocked on
  missing model credentials, tracked separately.
- CORS: replaced wildcard `allow_headers=["*"]` with explicit allowlist in
  `middleware/security.py` to comply with OWASP A05 when credentials are allowed.
- Auth stub: added `ENVIRONMENT` guard in `api/deps.py` (keyed on
  `settings.environment`, populated by the unprefixed `ENVIRONMENT` env var) so
  the dev-only `_extract_subject` shortcut raises `ConfigurationError` on startup
  in non-local environments. Also fixed `core/config.py` to read `environment`
  from the unprefixed `ENVIRONMENT` var via `validation_alias="ENVIRONMENT"` so
  the guard actually fires in deploy configs that set `ENVIRONMENT=production`.
- PII: `PiiGuardedProvider` wrapper class in `generation/guarded.py` screens both
  the system and user prompt blocks on every `GenerationProvider.complete()` call
  and raises `ValidationError` on a forbidden-PII match before the inner provider
  runs, so real-child PII can never be sent to an external LLM. The guard asserts;
  it does not scrub.
- Removed plaintext database credentials from `core/config.py`; moved example
  values to `.env.example` only.
- Enforced admin-approval invariant for published stories (Phase 3 slice 1): a
  story can reach a child profile only with a recorded admin approval. The
  guarantee is held by four layers: a frozen publish state machine
  (`publishing/state_machine.py`, illegal transitions raise
  `StateTransitionError` mapped to HTTP 409); a single write path
  (`publishing/service.py::approve` is the sole setter of `status="published"`,
  stamping `approved_by` and `published_at` atomically server-side, never from
  client input); read-path defenses on both `list_library` (INNER JOIN requiring
  `approved_by IS NOT NULL`) and `get_storybook_version` (non-admin callers get
  404, not 403, for any non-published/unapproved/non-current version, hiding
  draft existence); and an end-to-end invariant lock test. A new admin role
  screens content cross-family; guardians have no draft or approval access in
  this slice.
- Error responses no longer disclose caller-supplied `value` or internal
  lifecycle `context` (e.g. a resource's `status`) in the client-facing body;
  the full payload is retained in the server log only (CWE-209, red-team
  Finding 3). The `StateTransitionError` message was also genericized so it no
  longer names the internal current lifecycle state to the client; the full
  `from`/`action` detail stays in the server-side `context`.
- Closed-world domain types at the trust boundary (Phase 3 slice 1 review): the
  storybook lifecycle (`Status`/`Action`) and the principal `Role` are now
  `StrEnum`s, coerced from their ORM string columns at the boundary so an
  unmodeled status or role raises instead of silently flowing through. Backed at
  rest by two `CHECK` constraints (`ck_storybook_status`, `ck_user_role`) added
  in a new Alembic migration, so no non-API write path can persist a value
  outside the modeled set.
- Library listing hardened against malformed approved-story metadata
  (`api/library.py::_library_item`): boolean values are rejected where a number
  is expected, a non-finite reading-level target (NaN/Inf) can no longer reach
  the response and 500 the whole listing via Starlette's `allow_nan=False`, and
  any field falling back to a default now emits a structured
  `library_item_malformed_metadata` warning instead of degrading silently.

### Added
- Guardian console (C4a-4): an admin-only `GET /api/v1/review-queue` endpoint
  that lists `in_review` storybooks cross-family (mirroring the review-surface
  authorization) with a screened flag and flagged count, plus the frontend
  review console (severity-ordered queue) and a flags-first review-detail screen
  with pinned Approve / Send Back actions. Swipe-to-approve is deliberately
  excluded per ADR-005. The "Still processing" section reads the C4a-5
  guardian-only generation-jobs endpoint and self-degrades to an empty list for
  the admin reviewer (who receives a 403); the cross-family admin
  generating-jobs view is tracked in #74.

- Profile management (C4a-2): family-scoped profiles API (`GET`/`POST`
  `/api/v1/profiles`, `PATCH /api/v1/profiles/{profile_id}`), the kid-surface
  Profile Picker as the app's entry page (selection lands the child in their
  own library route), and a guardian Profiles page for creating and editing
  per-child age-band and reading-level caps with illustrated avatars (no
  child photos; preset-only avatars by decision, see issue #65).
- Design system: `AvatarCircle` component (preset avatar glyph with dashed
  initial fallback) plus its 8-preset avatar catalog, extracted from the C4a-2
  profile UI into `@cyo/design-system`, with tests and an authored design-sync
  preview. Child avatars are preset-only by decision (no photo uploads);
  generated illustrated art will replace the emoji glyphs (issue #65).
- Design sync: re-synced all 8 components to the claude.ai/design project,
  now with real per-component prop contracts (`dtsPropsFor` covers the
  `noEmit: true` gap that previously shipped stub `.d.ts` files), a
  conventions header for the design agent, and a `column` card layout fix
  for the Button preview.
- Adversarial safety evaluation of the generation and moderation pipeline (docs + tooling,
  no runtime paths touched): `docs/planning/safety/adversarial-safety-evaluation.md` records
  the six-class failure taxonomy, the threat model, and five model-independent structural
  findings verified at source, of which two are moderation-bypass seams (the import path in
  `generation/import_story.py` and the admin `POST /submit` in `api/approval.py` reach a
  publishable state with no `moderation_report`). A passage-oriented adversarial corpus
  (`docs/planning/safety/adversarial-corpus.json`) and a harness
  (`scripts/adversarial_harness.py`, with unit tests) feed the corpus to the real moderation
  stages and the PII guard, report a per-class catch-rate, and refuse to treat a mock run as
  evidence (exit 3). The previously-checked Phase 3 "adversarial briefs flag and route to
  human review" gate is reframed to partially-met across PROJECT-PLAN.md, roadmap.md,
  completion-plan.md (carried debt C3-SAFETY), and ADR-005: "no auto-publish path" holds, but
  the flagging claim has no live-model evidence and is false on the two bypass seams. Under
  the two-track model this is Track 1 debt and a Track 2 (Kids Category / COPPA) launch
  blocker; new risk-register rows track the bypass seams, the unbacked gate, and the interim
  dev-auth-stub trust assumption.
- Track 2 public-launch planning (docs only, no code paths touched): PROJECT-PLAN.md
  v2.3 adds Phases 6-9 (public auth and multi-tenancy, Kids Category/COPPA compliance
  and account lifecycle, Capacitor iOS shell with tiered Apple In-App Purchase, curated
  public catalog with hosted infrastructure and App Store submission), a deprecation
  register, Track 2 risks, metrics, and milestones M6-M9. Three new ADRs anchor the
  decisions: ADR-008 (public App Store launch with tiered subscription monetization),
  ADR-009 (Supabase platform for auth/Postgres/storage with pgmq queue evaluation),
  and ADR-010 (Modal moderation review backend and an evidence-gated Modal generation
  leg behind the `GenerationProvider` seam). The ADR index gains the missing ADR-007
  row and the three new rows.
- Phase 3 backend closeout. Two features that read/validate against a pinned story
  version: (1) C3-4 guardian review-surface read API, an admin-only
  `GET /api/v1/storybooks/{storybook_id}/review` that projects the stored moderation
  report into flagged passages (findings grouped by node with the node prose joined)
  plus story-level findings, shaped for the Phase 4a guardian console; and (2) Finding 2
  reading-state save integrity, a two-tier validator on `PUT` reading-state that runs a
  structural floor on every save (current_node exists; var_state keys are declared and
  in-bounds) and full deterministic engine replay when the optional `choice_path` is
  present, rejecting a forged or mismatched state with 422. The version-mismatch (409)
  optimistic-concurrency check runs before the version-existence check, so a stale-session
  save is a conflict, not a not-found. `choice_path` is optional this slice; making it
  required is tracked in the completion plan.
- K-12 storybook design system package at `frontend/design-system/`: 7 React
  components (`Button`, `ChoiceButton`, `Dialog`, `EmptyState`, `PassageText`,
  `ProgressBar`, `StatusBadge`) plus committed design-sync artifacts for
  deterministic re-sync to the CYO Design System project on claude.ai/design.
- Phase 3 slice 2: staged content-moderation review pipeline. Generated stories are
  screened between the deterministic gate and guardian review by a deterministic
  classifier pre-filter (OpenAI Moderation + Perspective), an LLM safety hard gate,
  LLM readability and branch-coherence soft gates with one bounded auto-repair pass,
  and an LLM engagement advisory. Hard blocks auto-reject to needs_revision; clean or
  repaired stories submit to in_review. Reviews run behind an independence-enforcing,
  PII-guarded review provider (OpenRouter/Ollama; Modal deferred).
- Story-skeleton structure diagrams: a deterministic PlantUML generator
  (`scripts/render_skeleton_diagrams.py`) plus a catalog and data-dictionary at
  `docs/architecture/story-skeletons.md`, with a drift-guard test.
- Unit test coverage raised from ~80% to 96.89% across all source modules:
  `api/health.py`, `api/deps.py`, `api/library.py`, `api/reading.py`,
  `utils/logging.py`, and the main `app.py` exception-handler matrix.
- Purge policy for `GenerationJob.report` documented in ADR-007
  (`docs/planning/adr/adr-007-raw-output-retention.md`): raw LLM outputs are to be
  purged 30 days after generation. This is a documented plan only; runtime
  enforcement (a scheduled job) is deferred to Phase 5 and is not yet active.
- Kid library page (C4a-3): "Continue Reading" hero with full-width progress bar,
  "More to Explore" shelf grid with per-book progress, tap-to-rate stars, and an
  explicit empty state (wireframe 4.2).
- Library API enrichment: `LibraryItem` now carries `node_count`, the child's
  `rating`, and a `progress` summary (visited nodes + last-activity timestamp)
  via two bulk queries.

### Changed
- Approval endpoints now return precise per-action response models
  (`SubmittedView`, `ApprovedView`, `SentBackView`, `ArchivedView`) instead of
  the single permissive `StorybookStateView`. `ApprovedView` makes `approved_by`
  and `published_at` required, so the response layer can no longer represent the
  illegal "published without an approver" state. This changes the OpenAPI schema;
  regenerating the frontend client is a documented follow-up (the admin endpoints
  are not consumed yet).
- ADR-005 (mandatory human approval) amended: the recorded approver in Phase 3
  slice 1 is a dedicated global admin (backend safety operator) screening content
  cross-family, not the child's own parent. The core invariant (no story reaches
  a child without a recorded human approval) is unchanged and strengthened.
- Removed `utils/financial.py` (template scaffolding with no domain role in a
  kids' reading app); template feedback logged in `docs/template_feedback.md`.
- Added `#CRITICAL`/`#ASSUME`/`#EDGE` RAD assumption tags to
  `player/engine.ts` and `offline/sync.ts` to match backend tagging practice.
- Documented single-process in-memory rate-limiter limitation in `SECURITY.md`
  with a Redis migration task added to the roadmap.

### Fixed
- Config env-name mismatch: `core/config.py` read `log_level`, `json_logs`, and
  `database_url` only under the `CYO_ADVENTURE_` prefix, but docker-compose and
  `docs/guides/configuration.md` set them unprefixed (`LOG_LEVEL`, `JSON_LOGS`,
  `DATABASE_URL`), so those compose-injected values were silently ignored at
  runtime. Each field now reads via `AliasChoices` accepting both names
  (`CYO_ADVENTURE_DATABASE_URL` stays first and wins if both are set, preserving
  the migrations/tests contract). Also corrected the `docker-compose.yml`
  `DATABASE_URL` default to the `postgresql+asyncpg://` driver that
  `create_async_engine()` requires; the sync `postgresql://` default was
  previously masked because the app ignored the variable entirely.
- Validator-player evaluator parity: the Python condition evaluator treated
  booleans as integers in ordering comparisons (`bool` subclasses `int`), so an
  ordering comparison involving a boolean (literal operand, bool-valued
  variable, or missing-variable default) evaluated numerically in the Layer-2
  validation walk while the TypeScript player failed closed; a story certified
  dead-end-free could dead-end in the browser. Both evaluators now fail closed
  identically (`storybook/evaluator.py::_ordered`), and the shared conformance
  corpus grows 27 to 42 cases pinning every route (the TypeScript suite passed
  all new cases unchanged). The condition grammar additionally makes
  divergence-capable input unrepresentable: comparison operands are literals or
  `{"var": name}` references only (both evaluators resolve nested-condition
  operands to literal false, never evaluate them), ordering operators reject
  boolean literals, and every story int literal (condition literals,
  `Variable.initial/min/max`, `Effect.value`) is bounded to |n| <= 1e9
  (`MAX_ABS_STORY_INT`) so exact Python ints and the client's IEEE-754 doubles
  stay exact for the bounded literal space; the reading-state floor rejects
  forged saves above 2^53 - 1. Full divergence matrix and maintenance contract
  in `docs/planning/evaluator-runtime-equivalence.md`; spec pseudocode and
  ADR-006's operator count corrected.
- Type safety at the approval and generation response boundary: the four approval
  handlers (`api/approval.py`) and the two generation-job responses
  (`api/generation.py`) passed a raw `str` status into response models whose
  `status` fields are closed-world `Literal`s, producing six BasedPyright
  `reportArgumentType` errors. The handlers now coerce the actual DB status via a
  quoted `cast` to the response Literal (so Pydantic revalidates the value at
  construction and a wrong status surfaces as an error rather than a false 200),
  and the enqueue response relies on its `"queued"` default. Adds a shared
  `JobStatusLiteral` alias so the job-status union lives in one place. No behavior
  change; `basedpyright src/` is now clean.
- Merge queue no longer stalls PRs. `pr-validation.yml` used a concurrency group
  keyed only on `github.event.pull_request.number`, which is empty on
  `merge_group` events, so concurrent queue entries collapsed into one group and
  cancelled each other's required `Dependency & Standards Validation` check; a
  cancelled required check blocks the merge. Added the `|| github.ref` fallback
  (matching the other required workflows) so each queue entry gets a unique
  group. Also stopped `sonarcloud.yml` from enforcing the quality gate inside the
  queue (`fail-on-quality-gate` now true only on `push`), which was failing every
  merge-group build with non-required check noise.
- Front-matter validator (`tools/validate_front_matter.py`) no longer gates
  commits on gitignored working files. It walks `docs/` from disk, so the
  intentionally untracked `docs/superpowers/` scratch plans were failing the
  pre-commit hook for every commit; it now filters paths through
  `git check-ignore` (git resolved via `shutil.which`, fail-open if absent).
- Docker build on the shell-free DHI hardened base. The DHI runtime image has no
  `/bin/sh`, `apt-get`, or `groupadd`, so the previous single-base Dockerfile
  could not run its builder `RUN` blocks or create the non-root user. The build
  now uses `python:3.12-slim-bookworm` for the (discarded) builder stage and the
  DHI hardened image only for the runtime stage, drops the unusable
  `apt-get`/`groupadd` steps, and runs as a numeric `USER 1000:1000`. `uv` is
  copied from the digest-pinned `ghcr.io/astral-sh/uv` image (a musl-static
  binary, so it is immune to the builder's glibc version).
- Skeleton diagram generator (PR #37 review follow-up): `skeleton_to_plantuml`
  now raises instead of silently dropping a node with a missing id or
  miscounting an ending with an unrecognized valence, and sanitizes ending
  titles against PlantUML quote-breakage. The catalog table builder escapes
  `|` in title/band cells so author text can't shift columns. The diagram
  generator script (`scripts/render_skeleton_diagrams.py`) no longer crashes
  uncaught on a missing `java` binary or a malformed `.puml`, and
  `resolve_jar`'s failure messages now distinguish a benign missing-jar skip
  from a security-relevant hash mismatch.

### Changed
- **Breaking (schema 2.0):** `Ending` now carries typed `valence` and `kind`
  instead of a free-form `type`; `StoryMetadata` requires `topology`. The
  exported JSON schema and the entire story/fixture corpus were migrated.

### Added
- CI: Claude Tier 0 baseline PR review caller
  (`.github/workflows/claude-baseline-review.yml`), a thin caller of the org
  reusable in `ByronWilliamsCPA/.github`. Part of the org-wide tiered-pr-review
  rollout.
- Compact story-size scale (`"compact"`): a tiered budget profile for smaller/quicker
  stories, with fewer nodes and shallower branch depth per age band than the standard
  profile. Threaded through the generation pipeline, L1-7 gate (`validator/layer1.py`),
  Stage A prompt (`generation/prompts.py`), and `scripts/yield_harness.py --scale compact`.
  The gate now reports a `WARNING` finding for age bands not yet covered by the compact
  profile rather than silently skipping enforcement.
- Config-driven six-band policy profile (`validator/band_profile.py`), now the
  single source of truth for per-band budgets (absorbing `layer1._BUDGETS`).
- Policy gate layer PL-15..PL-18, run in `run_gate` between Layer 1 and Layer 2
  and blocking on error: forbidden-ending-kind (age-gated no-death/capture),
  per-band content ceiling, ending/decision floors, and topology verification
  against a deterministic Ashwell classifier (`validator/topology.py`).
- Optional `Node.safety_scope` for downstream review scoping.
- Ollama provider HTTPS and HTTP Basic-auth support for the auth-proxied homelab
  host (Traefik + Authentik): reads the unprefixed `OLLAMA_BASE_URL` and
  `OLLAMA_AUTH` (`user:password`) env vars, attaches Basic credentials when
  present, and maps the unauthenticated `302` redirect to a leg-fatal
  `ProviderError` instead of parsing the redirect body as a completion.
- Ollama requests now stream (`stream: true`): the adapter accumulates the
  newline-delimited JSON chunks, so the timeout bounds time-between-chunks rather
  than total generation time (the homelab host is single-parallel with a cold
  start, so full stories can take minutes). Adds a dedicated
  `ollama_timeout_seconds` (default 300) separate from the cloud `llm_timeout`,
  and defaults `ollama_model` to `qwen2.5:14b` (a ~9GB general instruct model that
  live-tested as both fast and structurally valid; the 30B tags are too slow on the
  single-parallel host and the reasoning models waste the token budget on thinking).
  The stream request sends `Accept-Encoding: identity` so the
  homelab proxy's gzip-compress middleware is a no-op; compressing the stream
  buffered and dropped long (multi-minute) generations mid-stream.
- Optional `OLLAMA_CA_BUNDLE` setting: when the homelab host serves a
  privately-signed (Homelab CA) TLS cert, point this at the CA bundle and the
  adapter loads it on top of the system CA store so verification succeeds without
  disabling TLS verification. Unset uses the public CA store; the same setting
  keeps working once the host serves a publicly-trusted cert.
- Initial project setup and structure
- `environment` setting plus a fail-fast guard that refuses to start outside a
  local environment when the development default database URL is still in use
- Unit tests for the database, health, config, and security modules, restoring
  the 80% coverage gate
- Storybook schema v1 (`cyo_adventure.storybook`): Pydantic v2 models, a whitelisted
  in-house condition DSL (ADR-006), and JSON Schema export to
  `schema/storybook.schema.json`.
- Phase 0 specifications: runtime semantics, validator rule catalog, condition-evaluator
  spec, authorization matrix, and privacy/data-handling model.
- Effect/variable type-agreement validation (`inc`/`dec` require an int target; a `set`
  value must match the target variable type) and a `schema_version` compatibility check.
- Phase 1 reader MVP: a deterministic story player (Python reference engine plus a
  TypeScript port sharing a conformance corpus), a condition evaluator in both languages
  over the ADR-006 DSL, and the Layer-1 graph validator (rules L1-1 through L1-7).
- Reader API: SQLAlchemy models, the initial Alembic migration, a role-aware auth seam
  (dev stub), and reading-state GET/PUT with revision-based 409 reconciliation, version
  pinning, and `event_id` idempotency, plus completion recording.
- PWA reader: XState player machine, reader UI, IndexedDB cache, an offline write queue
  with idempotent replay, multi-device conflict reconciliation, and a service worker.
- Two hand-authored stories (Tier 1 and Tier 2) with a development seed script.
- Set effects on bounded int variables are now clamped at runtime and rejected at
  validation when the value falls outside the variable's declared `min`/`max`.
- Foreign-key constraint linking `reading_state` to its `storybook_version` row so a
  saved state cannot pin to a version that does not exist.
- Phase 2 validation gate: a breadth-first config-walk closure (`validator/walk.py`)
  driving the pure `StoryEngine`, Layer-2 state-space rules L2-9 through L2-12
  (`validator/layer2.py`), an advisory reading-level check (RL-13) using a
  dependency-free Flesch-Kincaid implementation, a Phase-2 safety stub (SAFE-14),
  and a combined `run_gate` runner ordering L1 -> L2 -> RL -> SAFE.
- Phase 2 authoring pipeline: a `GenerationProvider` protocol with a deterministic
  `MockProvider`, a `ConceptBrief` intake model with bounded free-text fields, a PII
  egress guard, bundled stage-prompt templates, and a staged orchestrator with a
  bounded repair loop and no-progress abort.
- Phase 2 async worker and API (PR-c): `concept` and `generation_job` database tables
  with an Alembic migration; an RQ async worker and provider factory (`build_provider`
  returns `MockProvider` by default; live providers raise `ConfigurationError` until
  Phase 2b wires them); guardian-only API endpoints for concept intake
  (`POST /api/v1/concepts`), story generation
  (`POST /api/v1/concepts/{id}/generate`), job status
  (`GET /api/v1/generation-jobs/{id}`), and re-validation
  (`POST /api/v1/storybooks/{id}/versions/{version}/validate`);
  and a mock-driven generation yield harness (`scripts/yield_harness.py`, run with
  `--provider` to swap providers). Live provider wiring (Claude/Ollama/OpenRouter
  HTTP clients) and the 60% yield measurement over a 20-story sample are deferred
  to Phase 2b; see `docs/planning/phase-2b-live-provider.md`.
- Phase 2b live generation providers: async OpenRouter and Ollama adapters (httpx)
  behind the existing `GenerationProvider` interface, a composite `FallbackProvider`
  cascade (`haiku-4.5 -> sonnet-4.6 -> ollama`) with cross-leg failover and a
  leg-fatal circuit breaker, and a `build_provider` assembler so the active backend
  is a configuration change. Includes a prompt restructure into a cacheable
  system/volatile-user split, a 20-brief live yield harness with provider isolation
  flags, and a pre-output orchestrator self-check (orphan delete, ending-count and
  depth reconciliation) that lifts the Tier-1 gate-pass yield to 70% (14/20) on the
  Haiku 4.5 primary. Closes ADR-003 acceptance criteria AC#1 and AC#2.
- Ratings: a child can rate a storybook 1-5 (`POST /api/v1/ratings`) and read back
  their ratings (`GET /api/v1/ratings/{profile_id}`). Ratings are per-child,
  per-book, mutable (re-rating overwrites), and family-scoped (a child cannot rate
  or list another profile's or family's books). Backed by a new `rating` table and
  Alembic migration. First phase of the ratings-and-family-sharing design.

### Changed
- Readiness probes no longer return raw exception text to clients; failures are
  logged server-side and a generic message is returned (OWASP A09)
- Removed the deprecated org `python-pr-validation.yml` caller; PR-title and
  conventional-commit validation are handled by `pr-title.yml` and `ci.yml`
- Raised the supported Python floor to 3.11 (`requires-python = ">=3.11"`); the Storybook
  models use `enum.StrEnum` and `typing.Self`, which require Python 3.11 or newer.
- Restricted Storybook state variables to `bool` and `int` in v1 (removed the unused
  `string` and `enum` variable types to match the condition-evaluator specification).

### Fixed
- `mkdocs --strict` docs build (dangling known-vulnerabilities template link)
- SBOM workflow caller now passes `no-build: false` for this installable package
- Windows compatibility matrix `ParserError` (test step pinned to `shell: bash`)
- REUSE compliance coverage for newly added files
- Documentation consistency (SECURITY.md SLA, requires-python, docs claims)
- Yield-harness dotenv loader now strips surrounding quotes, so a quoted
  `OLLAMA_AUTH="user:pass"` entry (as documented in `.env.example`) no longer
  leaks the literal quote characters into the Basic-auth credential.
- `_split_basic_auth` trims surrounding whitespace on each half so a stray-space
  `OLLAMA_AUTH` entry no longer produces a silent auth failure.
- An unusable `OLLAMA_CA_BUNDLE` path now raises a `ConfigurationError` naming the
  setting instead of a raw `FileNotFoundError`/`SSLError`.

### Security
- Refuse to send Ollama HTTP Basic credentials over a cleartext, non-loopback
  `http://` URL: a misconfigured `OLLAMA_BASE_URL` paired with `OLLAMA_AUTH` now
  raises a `ConfigurationError` rather than transmitting the password in
  reversible base64 over the wire.
- Stop tracking the empty `stack.env` file and add it to `.gitignore` (a
  Docker/Portainer stack env file that may hold real secrets).
- Replace realistic-looking credential strings in test fixtures with unambiguously
  synthetic values (`testservice:testcred`, `testpass`) to stop GitGuardian false
  positives on every PR; remove the real Authentik service account name (`svc-cyo`)
  from test code, comments, and script documentation; add `.gitguardian.yml` with
  an allowlist for remaining known-benign test patterns.

## [0.1.0] - TBD

### Added
- Initial project structure with Poetry package management
- Pydantic v2 JSON schema validation
- Structured logging with structlog and rich console output
- Pre-commit hooks (Ruff format, Ruff lint, BasedPyright, Bandit, pip-audit)
- Comprehensive test suite with pytest
- GitHub Actions CI/CD pipeline with quality gates
- CLI tool foundation
- License

### Documentation
- README with project overview and quick start
- CONTRIBUTING guidelines with development workflow
- References to ByronWilliamsCPA org-level Security Policy
- References to ByronWilliamsCPA org-level Code of Conduct

### Infrastructure
- Poetry dependency management with lock file
- pytest test framework with coverage reporting
- GitHub issue tracking and templates
- Automated dependency security scanning (Safety, Bandit)
- Code quality enforcement (Ruff, BasedPyright)
- CI/CD pipeline with multiple quality gates

### Security
- Bandit security linting
- Safety dependency vulnerability scanning
- Pre-commit hooks for security validation

[Unreleased]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/releases/tag/v0.1.0
