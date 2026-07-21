# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Backend HTTPS redirect (`HTTPSRedirectMiddleware`) had no path exemption, so a
  direct plain-HTTP liveness/uptime probe against a deployed backend container
  (bypassing the TLS-terminating reverse proxy) got a 307 instead of a real
  response, which most probes treat as down. Replaced it with
  `HealthExemptHTTPSRedirectMiddleware`, which exempts `/health/*` (read-only,
  GET-only) from the redirect while every other path still redirects.

## [0.25.0] - 2026-07-21

### Added

- ADR-021 story catalog import: a batch importer that runs the 25 authored draft
  stories through the deterministic validator gate and moderation into the review
  queue under the catalog family, plus a guarded catalog-publish command for
  admin promotion. Legacy schema 1.0 stories are normalized to 2.0 on import.

## [0.24.0] - 2026-07-21

### Added

- ADR-021 service accounts and row-level security: NOLOGIN `cyo_api` and
  `cyo_worker` Postgres roles with `service_rw` policies across the RLS-enabled
  tables, split API and worker async database engines with explicit pool sizing,
  and RQ worker entry points bound to the worker database session. Inert at
  runtime until the per-environment credential cutover.

## [0.23.0] - 2026-07-20

### Added

- ADR-021 Phase 1 worker observability: a non-gating generation-queue check on
  the readiness endpoint that reports queue depth plus stale and recently-failed
  jobs, an unprefixed `REDIS_URL` alias alongside `CYO_ADVENTURE_REDIS_URL`, and
  in-repo Redis and worker services in `docker-compose` for dev/CI parity, with a
  password-protected production Redis overlay, healthcheck auth, and resource
  limits.

### Security

- Bumped the transitive dev dependency `brace-expansion` from 2.1.1 to 2.1.2 in
  `frontend/package-lock.json` to clear GHSA-3jxr-9vmj-r5cp (CVE-2026-13149),
  flagged by OSV-Scanner. The advisory was published after this branch opened;
  no runtime dependency is affected (the vulnerable copy is pulled by `filelist`
  under the build toolchain).

## [0.22.1] - 2026-07-20

### Changed

- Reconciled `docs/planning/roadmap.md` and `docs/planning/PROJECT-PLAN.md` with
  actually delivered code: a 12-agent audit found both master planning documents
  had gone unupdated across roughly 20 releases, still marking Phases 4b, 4c, 4d,
  and most of Phase 6 as "Not started" despite substantial delivery in PR #270.
  Corrected phase-status tables, extended the ADR index from ADR-011 through
  ADR-019, fixed stale per-row status symbols in `capability-register.md`
  (bumped v1.6 -> v1.7), and surfaced previously untracked work (two child-safety
  gaps, the K19/content-diversity workstream, and several orphaned design docs).

### Fixed

- Production database migration deploy aborted mid-apply: `add_erasure_cascades`
  used bare `DROP CONSTRAINT` statements, one of which targeted an FK absent in
  production (`fk_story_request_anchor_storybook_id_storybook`), so the push
  failed with SQLSTATE 42704 and left the 0719/0720 migration batches unapplied.
  All 42 drops are now `DROP CONSTRAINT IF EXISTS` (idempotent and
  convergence-safe), and the migration is renumbered from `20260719190000` to
  `20260720170000` so it sorts after the merged 0720 batch and staging and
  production apply it in the same order (ADR-021, ADR-012).

## [0.22.0] - 2026-07-20

## [0.21.0] - 2026-07-20

### Added

- Catalog-time skeleton mutation (WS-5, D1-D8): a pure, offline authoring
  accelerator that grows distinct trees per cell by mutating already
  gate-verified skeleton shells, in `src/cyo_adventure/mutation/`. Five operator
  families re-proven by the byte-identical full gate plus a stricter WS-5
  acceptance harness: M1 sibling-subtree swap, M2 ending re-map within a valence
  class, M3 prune/graft within the cell envelope (same-band donors, contract
  merge/drop), M4 vary decisions-per-path (insert-linear/remove-linear/
  insert-decision), and M5 Tier-2 state variation (variable retune, gated-route
  rewire) with a single-walk ending-coverage and clock re-proof. Promotion-only
  anti-clone floors (`TAU_STRUCT`/`TAU_CELL`/`TAU_STATE`, calibrated by
  `scripts/calibrate_mutation_floors.py` into a committed baseline) and stage-4
  contract acceptance keep a mutant from cloning an existing tree or weakening a
  band floor. D8 adds the promotion bundle: a versioned `lineage.json` sidecar
  and writer with a hard parent-hash `--verify-bundle` check (`mutation/bundle.py`),
  the author re-guidance resolution flow (`mutation/reguide.py`), the stage-5
  deterministic mock sample fill (`mutation/sample_fill.py`), bounded operator
  chains (`mutation/compose.py`, `<= 3` ops per OQ-7), and the
  `scripts/mutate_skeleton.py` CLI (single-op, `--chain`, `--resolve`,
  `--verify-bundle`). No mutant reaches `skeletons/` or a child except through a
  reviewed human PR; the bundle lives in gitignored `out/mutations/`. Draft
  ADR-020 ("Mutation-derived skeletons and catalog growth", Status Proposed)
  records the decision set with a composed-chain bundle as its evidence exhibit.
- The catalog scanners' `*.contract.json` sidecar skip is generalized to a shared
  `is_sidecar` predicate that also skips the new `*.lineage.json` sidecar
  (`generation/skeleton.py`, ADR-020 decision 2 / OQ-1), so a lineage record in a
  band directory is never mistaken for a selectable skeleton.

### Changed

- Ratified ADR-020 (mutation-derived skeletons and catalog growth): status
  Proposed to Accepted; its six decisions now govern WS-6 (fresh-generation
  feed) and WS-8 (catalog flywheel).
- Raised the `src/cyo_adventure/mutation/` package branch coverage to 98%
  (tests only, one justified `# pragma: no cover`) to clear the codecov patch
  target for the WS-5 code.

## [0.20.0] - 2026-07-20

### Added

- Data-subject rights endpoints (GDPR Article 15/17/20, COPPA 312.6/312.10):
  `DELETE /api/v1/profiles/{profile_id}` erases a single child profile and
  every row linked to it; `DELETE /api/v1/me/family` erases a guardian's
  entire family account; `GET /api/v1/me/export` returns a full, portable
  JSON export of the family and its child profiles; `GET
  /api/v1/completions/{profile_id}` fills the one remaining child-linked
  table with no read path. Every family-/child-profile-owned foreign key in
  the schema now cascades or nulls out on delete (previously all `NO
  ACTION`, so a delete request could not have been executed at all without
  hitting an FK violation).
- Verifiable parental consent (GDPR Article 8(2), COPPA 312.5): a typed
  full-legal-name signature attestation layered on the guardian's existing
  OAuth login (`POST /v1/onboarding` with a `consent` payload), gating
  `POST /api/v1/profiles` (400 until recorded). Frontend:
  `GuardianConsentPage`, reached automatically via a new `needs-consent`
  auth status. Also fixes an unrelated, independently-discovered gap: the
  frontend previously never called `POST /v1/onboarding` at all, so a
  brand-new guardian's very first `GET /v1/me` would 401.
- Guardian self-signup admin-approval gate: an uninvited guardian's own
  first login now starts `User.status='awaiting_approval'` rather than
  `active`, blocking every authenticated endpoint (via the existing
  non-active-status rejection in `require_principal`) until an admin
  approves via `PATCH /api/v1/admin/users/{id}` (deny sets `deactivated`).
  Parallel to, and shares no state with, the existing admin-invite
  `pending` track. Frontend: `GuardianAwaitingApprovalPage`, reached via a
  new `awaiting-approval` auth status.
- A per-profile data-processing restriction flag (GDPR Article 18/21):
  `PATCH /api/v1/profiles/{profile_id}` with `processing_restricted: true`
  blocks new story-request submission for that profile (the point new data
  would reach a third-party LLM/classifier provider) without deleting any
  existing data.
- Two more scheduled retention-purge jobs (`generation_job.report` already
  had one, ADR-007): blocked/declined `story_request.request_text` is
  overwritten with a fixed placeholder 30 days after decision; stale
  `reading_state`/`completion`/`rating` rows are deleted 90 days after
  their profile's deactivation.
- Request interpretation and expectation-setting (WS-7 D1-D3, K19): a pure
  interpretation core (echo-safety floor, disposition derivation, and a fixed
  kid/guardian template catalog) plus a submission-time general layer that is
  persisted on each story request, reflecting the band promise, guardian
  banned-theme matches, and advisory safety findings without ever echoing
  premise-derived content for a blocked request (CR-1).
- Persistence for the interpretation: a nullable `story_request.interpretation`
  JSONB column (no backfill) with a daily pg_cron retention purge that nulls
  each element's premise-derived phrase on declined or blocked rows 30 days
  after decision, keeping the dispositions, reasons, and template texts.
- The refined interpretation layer (WS-7 D4-D6): a combined interpret-and-bind
  step returns the binder's element decomposition alongside the validated
  slot bindings, and the generation worker derives per-element dispositions
  from it (a degraded, keyword-decomposed variant for contract-less
  skeletons), attaches the result to the job/version report block as a sibling
  of the theme-contract audit block, and projects it onto the originating
  story request row.
- The rejection path and bounded re-route (WS-7 D7): on a theme a skeleton
  cannot bind, the worker retries the bind on up to two in-cell alternate
  skeletons (auto-pick only, contract-gated, recorded as `rerouted_from`)
  before failing closed; a failed bound-path fill now stamps an honest
  cannot-carry interpretation on both the failed job report and the request
  row. A PII egress block and a theme incompatibility are kept distinct by
  exception provenance (personal-details vs no-conforming-binding), and a PII
  block never triggers a re-route.
- The interpretation API surface (WS-7 D8, K19 exposed): the story-request view
  now carries the K19 interpretation as `RequestInterpretationView`
  (with `InterpretedElementView`), projected from the stored
  `story_request.interpretation` column by `_to_view` for every caller. It is
  a straight projection of the already-echo-safe stored object, so a blocked
  row surfaces the generic interpretation (every element phrase null) alongside
  the existing `request_text=None` redaction (CR-1), and a pre-WS-7 row (null
  column) projects to `null`.

### Security

- Cover images are now served exclusively via short-lived (1-hour) presigned
  R2 URLs, generated fresh on every read from the deterministic
  `{storybook_id}/{version}.webp` object key, instead of the permanent
  public URL previously stored and returned as-is. Closes the standing
  exposure where anyone who guessed or was handed a cover URL could view a
  specific child's cover art indefinitely without authentication. No R2
  object migration was needed (the key never changes); the stored
  `cover_image_url` column is now audit-only.
- Admin cross-family reads of child-linked data are now audit-logged: `GET
  /api/v1/admin/profiles` writes one `profile_viewed` `pipeline_event` per
  call (never one per row returned), queryable via `GET
  /api/v1/admin/audit?kind=profile_viewed` (GDPR Article 30 accountability).

### Documentation

- Added four more `docs/compliance/` artifacts, closing remaining low-dependency
  items in the remediation plan: an Article 17(3) balancing-test justification
  for indefinite `pipeline_event` retention (Phase 4d, inline in the
  remediation plan), an internal information security program document
  (`information-security-program.md`, Phase 6b), a breach-notification
  runbook (`breach-notification-runbook.md`, Phase 6c), and a Records of
  Processing Activities document (`records-of-processing-activities.md`,
  Phase 7a).
- Drafted three more counsel-review artifacts against the shipped Phase 2
  consent design: a Data Protection Impact Assessment (`dpia.md`, Phase
  7b), a guardian-facing Privacy Notice (`privacy-notice.md`, Phase 2c),
  and a processor DPA execution checklist with every link live-verified
  (`processor-dpa-checklist.md`, Phase 5).

## [0.19.0] - 2026-07-20

### Changed

- The primary Python runtime moved from 3.12 to 3.14 (#295): the production
  image now runs the hardened `dhi-python:3.14-debian13` base (whose
  interpreter lives at `/usr/bin/python3.14`, not the 3.12 image's
  `/opt/python/bin`), the required CI gate and the compatibility matrix now
  cover 3.14, and Renovate is restricted to digest-only updates for the two
  Dockerfile base images so the builder and runtime stages can never
  version-drift independently again. `requires-python` stays `>=3.11`;
  3.11-3.13 remain supported and tested.
- CI: release-automation PRs (`release.yml`'s `propose` job opens
  `chore(release): vX.Y.Z` against a `release/v*` branch, touching only
  `pyproject.toml`/`uv.lock`/`CHANGELOG.md`) now skip the full test/build
  matrix entirely instead of re-running it up to three times (`pull_request`,
  `merge_group`, and the post-merge `push`) over a diff whose underlying code
  was already fully tested by the feature PR that triggered the release.
  Added a `detect-release-pr` job to `ci.yml` (gates `ci`, `frontend`,
  `design-system`, `contract`, `detect-api-collection`/`api-tests`, and
  `coverage-upload` transitively via `ci`'s result; `ci-gate` treats a
  release PR's all-skipped state as a pass) and to `sbom.yml` and
  `container-security.yml` (both path-filter on `pyproject.toml`/`uv.lock`,
  which every release PR touches, and `container-security.yml`'s job builds
  a real Docker image to scan). On `pull_request`/`push` the detection reads
  the branch name/commit message directly; on `merge_group` the event's own
  `head_ref` is the synthetic queue ref, not the source branch, so the job
  extracts the PR number from it and looks up the real head branch via the
  GitHub API. Trade-off: a `uv lock` re-resolve on the release PR could in
  principle pick up a newly-published transitive dependency version untested
  by the original feature PR; accepted, since the weekly scheduled scans and
  the next feature PR's own full run remain the backstop.

## [0.18.4] - 2026-07-20

### Fixed

- Testing: `DeviceAuthorizedRoute.test.tsx`'s "parks the adult gate after the
  async IndexedDB-mirror path authorizes too" test asserted
  `isAdultGateWarm('u1')` immediately after `findByText('Kid picker')`
  resolved. `DeviceAuthorizedRoute.tsx` parks the gate in a second passive
  effect keyed on `status`, separate from the effect that resolves
  hydration; `findByText`'s `MutationObserver`-driven resolution could race
  ahead of that second effect's flush, intermittently failing the assertion
  even though the gate was genuinely parked moments later. The assertion
  now runs inside `waitFor`, matching the standard Testing Library idiom
  for effect-driven side effects after an async state transition, instead
  of asserting at one indeterminate point in the microtask queue. Verified
  locally: 20 consecutive runs of the file, all passing, plus the full
  frontend suite (113 files, 1385 tests).

## [0.18.3] - 2026-07-20

### Fixed

- Docs: added the missing YAML front matter to
  `docs/reviews/comprehensive-review-2026-07-17.md` and
  `docs/testing/{README,coverage-matrix}.md`, and added the `privacy` tag to
  `docs/_data/tags.yml`'s allow-list (used by
  `docs/compliance/gdpr-compliance-review.md` and
  `docs/compliance/coppa-gdpr-remediation-plan.md` but never added when
  those files were introduced). The local `validate-front-matter`
  pre-commit hook scans the whole `docs/` tree on every commit, so these
  gaps were silently blocking every local commit to the repo since the
  originating PRs merged.

## [0.18.2] - 2026-07-20

### Changed

- CI: stopped re-running the frontend, design-system, OpenAPI contract-drift,
  coverage-upload, and API-tests jobs in `ci.yml` on `merge_group` events,
  since they validate file content already checked on the PR run rather than
  merged-state validity; `ci-gate` now treats their intentional `skipped`
  result as passing. Dropped `merge_group` entirely from
  `security-analysis.yml`, `sonarcloud.yml`, and `reuse.yml` (all
  file-content-only scans that already ran on the PR and are re-confirmed by
  the existing push-to-main trigger). Removed `dead-code` and `link-check`
  from running on `merge_group` in `pr-validation.yml` (both already
  advisory-only in `validate-dependencies`). Removed the `pull_request`
  trigger from `python-compatibility.yml`, which duplicated `ci.yml`'s
  required Python 3.12 test run on every PR; its weekly schedule and
  push-to-main trigger still cover 3.11/3.13 compatibility drift. Together
  these remove the largest source of duplicate work between a PR's own CI run
  and the merge-queue's re-run of the same commit.
- CI: `sonarcloud.yml` no longer runs on `pull_request` at all (only `push`
  to `main`/`develop` and `workflow_dispatch`). Job-level timing data from
  recent PRs showed the job costing ~12 min per PR, ~11 of which was a
  duplicate full pytest run (on Python 3.14, for coverage.xml) rather than
  the sonar-scanner analysis itself (well under 90s); `fail-on-quality-gate`
  was already forced off outside `push`, so the PR-time run was always
  advisory with no way to act on the result. A `no-build: true` variant was
  tried to keep fast static-only PR feedback without the pytest run, but
  `--no-build` requires a pre-built wheel and this project has none (local
  editable install only), so `uv sync` hard-fails; reverted rather than
  pursued further without reading the reusable workflow's source first.
  `push` to `main`/`develop` keeps the full coverage-generating,
  gate-enforced run so the SonarCloud dashboard's coverage% stays accurate.
- Testing: added `-n=auto` (pytest-xdist) to `[tool.pytest.ini_options]`
  addopts. CI's Integration Tests job runs 827 tests serially in ~9.5 min;
  `tests/integration/conftest.py`'s Postgres container fixture is
  session-scoped, so each xdist worker gets its own independent
  `testcontainers` instance rather than sharing one, with no cross-worker
  isolation work needed. Verified locally with real Docker: 139 integration
  tests, 104.33s serial vs 42.18s at `-n 4`, all passing, coverage combining
  correctly across workers. `nox -s mutate` (mutmut) is unaffected, since
  `[tool.mutmut]` already resets addopts to empty before building its own
  pytest invocation.
- Testing: `tests/integration/conftest.py` creates the Postgres schema once
  per test session (via a throwaway sync `psycopg` engine, avoiding any
  asyncio event-loop entanglement) instead of once per test. Each test now
  resets its data with a single multi-table `TRUNCATE ... RESTART IDENTITY
  CASCADE` instead of a `drop_all`/`create_all` DDL cycle, which is
  materially cheaper since it never touches table/constraint/index
  definitions. The `engine` fixture is otherwise unchanged (still a real
  per-test `AsyncEngine` with `NullPool`), so the tests and `scripts/
  seed_dev_data.py` call sites that bind sessions directly to `engine` need
  no changes. Verified locally: all 827 integration tests pass unchanged.

### Fixed

- Testing: `test_malformed_min_verdict_row_is_skipped_with_warning`
  (`tests/integration/test_threshold_policy_loader.py`) drops the
  `ck_moderation_threshold_min_verdict` CHECK constraint to exercise the
  loader's malformed-row handling, but never restored it. That was safe
  under the old per-test schema rebuild; under the new session-scoped
  schema (see above), the dropped constraint leaked into any later test in
  the same xdist worker, intermittently failing
  `test_bad_min_verdict_insert_rejected_by_check` depending on test order.
  The test now restores the constraint in a `finally` block. Also
  deduplicated the catalog-family seed insert (`_pg_url` and `engine`
  fixtures) into a shared `_seed_catalog_family_stmt()` helper.
- CI: restored the `merge_group` trigger on `security-analysis.yml` and
  `reuse.yml`, dropped earlier in `[Unreleased]` above as file-content-only
  and not merged-state-sensitive. In practice the org ruleset requires
  "Security Gate Validation" and "REUSE Compliance" as status checks
  regardless of event context, so the merge queue waited forever for a
  check that could never report on a `merge_group` entry; confirmed live
  when the PR carrying this exact change was kicked from the queue with
  `CI_TIMEOUT`. Both scans are fast (bandit/OSV-Scanner and a license-header
  check, no pytest/build cost), so restoring them on `merge_group` is cheap
  and needs no org-level ruleset access to fix.

## [0.18.1] - 2026-07-20

### Changed

- Testing: `tests/integration/conftest.py` creates the Postgres schema once
  per test session (via a throwaway sync `psycopg` engine, avoiding any
  asyncio event-loop entanglement) instead of once per test. Each test now
  resets its data with a single multi-table `TRUNCATE ... RESTART IDENTITY
  CASCADE` instead of a `drop_all`/`create_all` DDL cycle, which is
  materially cheaper since it never touches table/constraint/index
  definitions. The `engine` fixture is otherwise unchanged (still a real
  per-test `AsyncEngine` with `NullPool`), so the tests and `scripts/
  seed_dev_data.py` call sites that bind sessions directly to `engine` need
  no changes. Verified locally: all 827 integration tests pass unchanged.

### Fixed

- Testing: `test_malformed_min_verdict_row_is_skipped_with_warning`
  (`tests/integration/test_threshold_policy_loader.py`) drops the
  `ck_moderation_threshold_min_verdict` CHECK constraint to exercise the
  loader's malformed-row handling, but never restored it. That was safe
  under the old per-test schema rebuild; under the new session-scoped
  schema (see above), the dropped constraint leaked into any later test in
  the same xdist worker, intermittently failing
  `test_bad_min_verdict_insert_rejected_by_check` depending on test order.
  The test now restores the constraint in a `finally` block. Also
  deduplicated the catalog-family seed insert (`_pg_url` and `engine`
  fixtures) into a shared `_seed_catalog_family_stmt()` helper.

## [0.18.0] - 2026-07-19

### Security

- The PII egress guard (`assert_prompt_pii_safe`) now also screens every
  prompt for email-, phone-, and street-address-shaped content, independent
  of the registered-child-name allowlist, closing the gap where a free-typed
  story premise could carry a sibling's contact details or a home address
  past the exact-match-only guard. Two previously unguarded egress paths are
  now covered by the same guard: the cover-art prompt sent to Google Gemini,
  and the Stage-0 safety-classifier calls (OpenAI Moderation, Google
  Perspective) in both the generation-time moderation pipeline and the
  node-edit review path (#304).

### Documentation

- Added a GDPR-specific compliance review and a phased COPPA/GDPR/GDPR-K
  remediation plan under `docs/compliance/`, companion documents to the
  existing COPPA compliance audit (#304).

## [0.17.0] - 2026-07-19

## [0.16.0] - 2026-07-19

### Added

- Story-diversity system (WS-0): an anti-template guard and a request-time
  similarity query, plus a Phase 2 eval harness (ECS/PS/RAR and lexical metrics,
  a committed fixture panel and baseline, the `run_diversity_eval` CLI, a
  `diversity_eval` nox session, and a per-PR `diversity` CI regression gate)
  (#300).
- Similarity-driven skeleton auto-selection (WS-4): request-time selection
  de-weights recently- and similar-theme-used skeletons and surfaces
  TREE/LEAF/CATALOG escalation so a family's repeat similar-theme request is
  steered to a different skeleton (#300).
- `import_cli --series-id` links an imported book into a series on import;
  an L2-13 large-Tier-2 scale advisory in the validator; two new skeletons,
  `the-cinderwick-exchange` (10-13) and `the-blackwood-sanatorium` (16+) (#300).
- Parameterized-skeleton theme contracts (WS-2, ADR-019): each production
  skeleton now carries a `<slug>.contract.json` sidecar declaring per-slot
  `{SLOT}` tokens (in beats guidance, ending titles, and choice-label
  templates only, never final prose) with a machine-readable safety envelope,
  and the full catalog is migrated. A deterministic slot validator
  (`validator/slots.py`) enforces completeness, an LLM01 injection charset, a
  word cap, versioned denylist bundles unioned with a band-mandatory floor,
  and per-slot distinctness/legacy-leak checks; `binding.py` binds a theme and
  fail-closed renders the bound skeleton (no residual tokens, structure
  fingerprint preserved, gate not blocked, byte-preserved FILL directives).
  New tooling: `scripts/parameterize_skeleton.py`, `scripts/bind_theme.py`,
  and the `scripts/check_theme_contract.py` acceptance gate (#303).

### Changed

- The generation worker now dispatches on theme-contract presence: a skeleton
  with no sidecar takes the byte-identical WS-1 free-text fill path, while a
  skeleton with a contract is bound, rendered, and bound-filled with a
  `theme_contract` audit block, fail-closed with no free-text fallback (#303).

- Choice labels are now diversity leaf content: excluded from the
  `structure_fingerprint` and folded into the anti-template guard's leaf
  distance and entity masking, with `check_fill_integrity` aligned. The Stage 1
  fidelity reviewer now also checks per-choice label intent, preserving the
  semantic guarantee the removed byte-level label check nominally provided
  (WS-1) (#300).

### Fixed

- Moderation auto-repair no longer silently replaces an imported story with a
  mock stub: a repair that changes the story's identity (id, tier, node count)
  is rejected and the story routes to review with its real content intact
  (#300).

## [0.15.0] - 2026-07-18

## [0.14.0] - 2026-07-18

## [0.13.0] - 2026-07-18

## [0.12.1] - 2026-07-18

### Fixed

- Device-grant revocation is now idempotent: a repeated `DELETE` no longer
  overwrites the original `revoked_at`, preserving the first revocation
  instant (#253).
- The child-session mint no longer leaks a cross-family existence oracle to a
  device grant: a nonexistent profile and another family's profile now return
  an identical 403 body, and the family check precedes the deactivation check
  (#249).
- Stage-0 moderation classifiers handle a non-finite (`NaN`/`Infinity`) score
  symmetrically: both OpenAI and Perspective now treat it as an absent score
  and degrade gracefully instead of silently dropping it (OpenAI) or raising a
  `ValueError` that aborted the whole safety batch (Perspective) (#144).
- The guardian/child/device token families are now a checked invariant: a
  startup validator asserts the three audiences are pairwise distinct and the
  two backend HS256 secrets differ, and a shared strong-secret validator keeps
  the child-session and device-grant checks from drifting (#251, #254).
- The served OpenAPI schema now documents the real API contract: bearer auth
  as a proper security scheme on every authenticated operation (the Authorize
  control now works in `/docs`, and generated clients see the requirement),
  the 401/403/404/409 error envelope on each operation that can produce one,
  a description for every router tag, and the installed release version
  instead of a hardcoded `0.1.0`. `/health` reported the same stale `0.1.0`
  and now tracks the release too.

### Added

- Device grants now persist an `expires_at` (stamped at mint from the token
  TTL), and the active-device list excludes unrevoked-but-expired ghosts so
  "present in the list" means "actually usable" (#252).
- Catalog-origin (admin-initiated) story requests: an admin authoring a
  request with no family targets a well-known system catalog family, so
  catalog content flows through generation and publish without making
  `family_id` nullable across the request/concept/storybook tables (#173).
- Postman/newman API coverage for 20 previously untested operations (67 of
  the 83 now registered; the 16 added by the M4b-d family-tier wave and the
  2026-07-17 remediation still need folders, see docs/api/README.md): child sessions, device grants
  (including online revocation enforcement), onboarding idempotency, the
  admin user/profile consoles, family connections, the moderation dashboard,
  the admin story-request queue, series continuation, and admin family
  create/rename. The local compose stack ships benign dev token-signing
  secrets so the mint endpoints are testable end to end.

### Documentation

- Synced the architecture diagram set and companion docs with the current code
  (through v0.11.0, PRs #270 and #277). The ER diagram and data model now cover
  all 22 tables (adds `family_connection` + `kid_flag` and the ADR-015/016
  cost-gate and consent columns); the API/C4/system-overview/README references
  reflect 28 routers; the validator gains PL-22; moderation repair now re-runs
  the full validation gate and the admin re-screen sweep is shown; the event log
  is 20 event types; cover art storage (Cloudflare R2, ADR-017) is added; and the
  sitemap/journeys pick up the new admin and family surfaces (master library,
  audit, user management, reading-visibility, connection consent,
  recommendations, kid flags, passage editor). Regenerated every affected SVG.

## [0.12.0] - 2026-07-17

### Added

- Comprehensive security, UX, and design review (`docs/reviews/`) plus a tiered
  remediation plan, and the remediation of most of its findings.
- Reader text-size control (A/A+/A++, persisted per profile) and an offline
  library shelf so an offline kid can still reach their downloaded books.
- Admin review-queue flow-through (auto-advance + queue position), triage
  metadata (age band, waiting time) on queue rows, and a new admin master
  library (`/admin/library`, `GET /v1/admin/storybooks`) to browse and re-open
  any story in any lifecycle status.
- Admin operator endpoint to force-fail a stuck generation job.
- A manually-triggered CI workflow to regenerate Playwright visual-regression
  baselines on the runner and commit them back with a verified signature.

### Fixed

- Generation pipeline no longer strands jobs at `running` or double-executes
  them after a hard worker death; the condition validator is depth-capped
  against `RecursionError`.
- A failed or unconfigured moderation classifier now surfaces a visible
  degraded advisory instead of silently contributing nothing.
- Kid routes no longer fall back to the guardian bearer and the reader refuses a
  mismatched profile (closes cross-profile reads online and offline).
- Library shows "Finished!" for completed books instead of a misleading page
  count; several kid-surface tap targets, recovery links, and copy fixes.
- Guardian/admin "Please reload" dead-ends became inline retry; muted-ink token
  raised to WCAG AA.

### Changed

- Security hardening: TrustedHost activation, untrusted-input prompt fences,
  correlation-middleware ordering, hidden production source maps, cache purge on
  sign-out.
- Supply chain and dev hygiene: Renovate manages container image digests and
  pre-commit; nox extras fixed and Python 3.10 legs dropped; codecov
  safety-critical gate extended.

## [0.11.0] - 2026-07-17

### Added

- Capability register (K/G/A/S IDs) as the project's scope contract, with
  ADR-015 (story initiation and gating), ADR-016 (three-ring social
  boundary), ADR-017 (AI cover art), and ADR-018 (children's privacy
  compliance, Proposed), plus the traceability review, test traceability
  matrix, and re-anchored roadmap milestones.
- M4b editor and engagement wave: read-aloud, endings tracker, kid feedback
  flag, enforced content controls, per-child permissions, review skim aids,
  and a prose-only passage editor that re-runs the validation gate and
  moderation on every edit.
- M4c family loops: notification infrastructure with a guardian bell,
  guardian reading-visibility page, kid-friendly generation status, and the
  ADR-015 budget consent gate with per-child auto-approve envelopes and a
  balance surface.
- M4d connections: dual-guardian connection consent, an enforced ring-2
  recommendation boundary guard, and cousin recommendation chips on the kid
  shelf.
- Daily production E2E workflow with pinned-issue alerting.

### Fixed

- Moderation repair now re-runs the full validation gate on every adopted
  repair, and the band-policy validator (PL-22) fails closed.
- Generation quota is now debited on the legacy intake path, and the
  generation report is restricted to admins.

## [0.10.0] - 2026-07-17

## [0.9.0] - 2026-07-17

### Added

- Strict FIPS compliance gate (ADR-013). The FIPS checker gains a
  `--fail-level {error,warning,info}` flag and an acknowledged-findings
  baseline in `pyproject.toml` (`[tool.fips_check.acknowledged]`): each
  acknowledgment needs a reason, a citation into the crypto inventory, and
  a reviewed date that expires after 90 days, matching the ADR-013
  quarterly review. CI now runs at `--fail-level info`, so every finding
  must be fixed or freshly acknowledged; errors can never be baselined.
  New runtime assertions (`tests/unit/test_fips_runtime_assertions.py`)
  mechanically back the acknowledged dispositions: dependency floors for
  `cryptography` and `pyjwt`, OpenSSL 3.x links, a TLS 1.2+ default-context
  floor, and the asymmetric-only JWT allowlist validator. Two new CI jobs
  assert the runtime image's ML-KEM-capable OpenSSL 3.5 line: a Debian 13
  container run of the assertion suite and a shell-free check inside the
  pinned production base image digest.
- Mutation scoring shared by CI and `nox -s mutate` (`scripts/mutation_score.py`).
- Weekly mutation and fuzzing workflows file a `ci-failure` tracking issue on a
  failed scheduled run so schedule-only breakage cannot stay silent.
- Hypothesis `ci`/`dev` settings profiles and generative player-engine property
  tests; adversarial-corpus tests under the `ai_security` marker; negative-path
  tests for the cover-art subsystem; generation-boundary malformed-output tests;
  true-concurrency reading-state tests; and JWT time-boundary tests.

### Fixed

- **Security (PII egress):** the prompt PII guard now NFKC-normalizes and strips
  zero-width / format and control characters before matching, closing confirmed
  bypasses (zero-width insertion, compatibility-form spelling, control chars)
  that let a real-child name reach an external LLM provider. Confusable
  homoglyphs remain a documented residual.
- **Mutation testing** now runs: rewrote `[tool.mutmut]` in the mutmut 3.x
  dialect (the stale 2.x keys crashed mutmut 3.6 at startup) and replaced the
  broken org reusable workflow call with a self-contained, scored weekly job.
- **Continuous fuzzing** now exercises real code: replaced the no-op template
  harness with condition-evaluator and Storybook-validation Atheris targets and
  seed corpora.
- Docker-less test runs no longer exit non-zero: a failed testcontainer Docker
  probe leaked a socket that `filterwarnings=["error"]` escalated at teardown.
- FIPS checker no longer flags domain `seed()`/`idea()` method calls as the
  SEED/IDEA block ciphers; ambiguous cipher names now require cryptographic
  context (a crypto-library import or a crypto namespace in the call chain).
- The FIPS workflow's failure gate now actually fires: the checker's exit
  code was previously swallowed by a `tee` pipeline without `pipefail`, so
  the job always passed while the PR comment could say FAILED. Trigger
  paths now also cover `tests/`, the checker script, and the `Dockerfile`.

## [0.8.0] - 2026-07-17

## [0.7.0] - 2026-07-17

### Added

- Admin user management console (`/admin/users`). An admin can now create,
  reassign, and activate/deactivate guardians, admins, kid profiles, and
  families from one console, plus curate a new directional family-connection
  allowlist for a future cross-family recommendation feature. None of this
  existed before: families and guardians were only ever created implicitly
  via Supabase JIT onboarding, and there was no admin path to manage a kid
  profile in another family or a family's active/deactivated status.
  Admin-created guardians/admins start as a `pending` invite (no Supabase
  Admin API integration exists in this codebase) that binds to a real account
  by exact email match on that person's first Supabase login. Deactivating a
  family cascades to deactivate its members in one transaction; reactivating
  a family does not auto-reactivate them.

## [0.6.0] - 2026-07-16

### Added

- Comprehensive UX pass across the app. Kid readers can undo their last
  choice (go back one page), see clearer library actions with PIN badges
  and rating feedback, and get kid-safe polish for loading, conflicts, and
  endings. Guardians get responsive intake forms with hints and counters,
  request-age and recovery context on pending requests, confirm-before
  dialogs for approve and decline, and a pending-request badge. Admins get
  a severity/search/refresh review queue, a navigable story-graph
  read-through, guarded moderation-config changes with readable history,
  and a side-by-side compare view against a story's previous version. A
  global toast channel confirms actions, including synced reading, across
  the app. The app is installable as a PWA, and the design system supports
  dark mode via `prefers-color-scheme`.

### Fixed

- Distinguish offline, rate-limit, and server errors in the error boundary
  instead of a single generic failure message.
- Honor the login return path after sign-in, style dead-end states, and
  add a sign-in watchdog.
- Give permanently lost reading-progress saves honest copy distinct from a
  save that is still retrying.
- Hide the read-aloud toggle until the reader ships text-to-speech.
- Fix two real phone-width layout bugs in the guardian console found by
  measurement.
- Meet AA contrast, 44px touch targets, and reduced motion in the design
  system.
- Fix cross-origin service worker caching so the app installs and updates
  correctly as a PWA.

## [0.5.2] - 2026-07-15

### Fixed

- Kid devices could hit a dead-end crash on the "I am a grown-up" link and a
  bounce-to-login on "Add Child". Two independent stale-deploy and device-grant
  bugs are fixed. First, a returning client whose service worker still served an
  older app shell referenced deleted, content-hashed chunk filenames; the next
  cross-chunk navigation 404'd and dropped the reader into the "Something went
  wrong" boundary. Route chunks now load through `lazyWithReload`, which forces
  exactly one `location.reload()` on a stale-deploy chunk-load failure (guarded
  by a per-chunk one-shot flag so a genuinely missing asset does not loop, a
  watchdog so a no-op reload surfaces the error instead of hanging, and a
  chunk-load-error check so transient or unrelated failures fall straight
  through). Second, on an ADR-014 device-grant-only kid device the "Add Child"
  tile linked to the guardian-gated profile route, bouncing the child to the
  password screen; the tile is now shown only when a guardian session is present
  on the device and stays in sync with a cross-tab guardian sign-in or sign-out.

### Security

- Refuse to start a deployment that is silently defaulting to the `local`
  environment. When `ENVIRONMENT` is unset, `Settings` falls back to `local`,
  which trusts the dev auth stub (the bearer string is accepted as the request
  subject) and disables the in-memory rate limiter. A deployment that forgot to
  set `ENVIRONMENT` would therefore come up fully open. Startup now fails fast
  with a `ConfigurationError` when `ENVIRONMENT` is unset but OIDC verification
  config is present (the marker of a real deployment, never set by local, CI,
  or e2e runs), naming the fix. Local, CI, and e2e runs are unaffected because
  they set no OIDC config.
- The in-memory rate limiter now activates only outside `ENVIRONMENT=local`,
  matching the dev auth stub's own gate so local and e2e runs are not throttled
  while every deployed environment keeps per-IP limiting.

## [0.5.1] - 2026-07-14

## [0.5.0] - 2026-07-14

### Added

- Guardian password recovery (ADR-009). The sign-in page now offers a "Forgot
  your password?" request that emails a reset link, with an
  enumeration-resistant confirmation that never reveals whether an account
  exists. Following the link back to the login page detects the recovery
  session and shows a "Choose a new password" form (client-side match and
  minimum-length checks) instead of dropping the guardian into the console;
  once the new password is saved, the app auto-continues to the role-based
  console. Previously a recovery link established a session but offered no way
  to actually set a new password.

### Fixed

- Guardian login could loop back to the sign-in page indefinitely on a device
  that had cached an older build. The frontend nginx config served the service
  worker control scripts (`sw.js`, `registerSW.js`) with `Cache-Control:
  public, immutable, max-age=1y`, the same rule meant only for content-hashed
  `/assets/*` files. Because those scripts keep a stable filename across
  deploys, an immutable header could pin a browser to a stale service worker
  that kept serving an old precached app shell across reloads, so a fix never
  reached that client. They are now served `no-cache` via exact-match nginx
  locations, letting the PWA auto-update swap in a new service worker on the
  next load. A browser already wedged on the old worker still needs a one-time
  clear-site-data or hard reload; new and cleared clients self-heal.

### Security
- Suppressed four unfixable `gawk` CVEs (CVE-2026-40467, CVE-2026-40468,
  CVE-2026-40469, CVE-2026-40553) in the Debian 13 base image via
  `.trivyignore`; all report an empty Fixed Version upstream. `gawk` ships in
  the hardened base image and is never installed or invoked by the app, so the
  vulnerable paths are unreachable. Documented in
  `docs/known-vulnerabilities.md` with a 2026-09-12 reassessment date. Keeps
  the container vulnerability scan green without relaxing the CRITICAL/HIGH
  gate for fixable findings.

## [0.4.0] - 2026-07-14

### Added
- Device-authorized kid access (ADR-014). The kid surface (`/kids`,
  `/library/*`, `/read/*`) is now gated by a per-device grant instead of an
  ambient guardian session: a guardian authorizes a device once (from the
  console "This device" section, or by handing a fresh device to a child from
  the landing "Kids" door, which routes through login with an
  `authorize-device` intent), and the child then reads without an adult
  signing in each time. The two former per-page parental gates collapse into a
  single `AdultGate` at the adult-subtree root, so adult-to-adult navigation
  (guardian to guardian, guardian to admin, admin to guardian) no longer
  re-challenges once warm; only crossing up from the kid surface re-locks it.
  Post-login redirect is now role-based (admin-only adults land on the admin
  console, guardians and dual-role adults on the guardian console).

### Documentation
- Refreshed the architecture doc set and diagrams for ADR-014 (data model,
  authorization matrix, tech spec, deployment, C4 context, API-persistence
  component, ER, and the three user-journey diagrams), and added two new
  diagrams: a device-grant sequence diagram and a route/page
  sitemap-and-flows diagram.

## [0.3.0] - 2026-07-14

### Added
- Guardian parental gate: a "Not you? Sign out and use a different account"
  link on the locked-challenge screen, for guardians who cannot
  re-authenticate as the current session's owner (a test account, or one
  whose password identity differs from the signed-in session). Signs out
  through the existing `signOut()` flow; `ProtectedRoute` redirects once the
  session clears.

### Fixed
- Release-bump commits are now signed and self-verify before the release PR
  is opened. `createCommitOnBranch`'s `branchName` was populated with a
  fully-qualified ref (`refs/heads/release/vX.Y.Z`) instead of the
  unqualified branch name the GitHub GraphQL schema requires, which would
  have made every real invocation fail branch resolution; fixed to pass the
  unqualified name. Also hardened the ref-reset/commit-creation call with a
  bounded retry against the transient `expectedHeadOid` mismatch possible
  from the REST-then-GraphQL write ordering, and stopped `set -e` from
  swallowing the intended failure diagnostic when GitHub returns a
  GraphQL-level error.
- The `createCommitOnBranch` request body no longer fails with `jq: Argument
  list too long` on real invocations: `uv.lock` alone base64-encodes to
  roughly 1MB, and passing that (plus `pyproject.toml`/`CHANGELOG.md`) as
  `jq --arg`/`--argjson` command-line arguments could exceed the runner's
  `ARG_MAX` once combined with the environment footprint. File contents are
  now read via `jq --rawfile` from temp files instead of the command line,
  and both prior `jq` calls are collapsed into one so no intermediate
  large-string variable is ever placed back on argv. Also distinguishes a
  genuine `HTTP 404` (branch does not exist yet) from any other branch-
  lookup failure, retrying the latter instead of misrouting it into a
  branch-creation call against a branch that already exists.

### Added
- Manual production smoke e2e tier (`frontend/e2e-prod/`, `npm run test:e2e:prod`):
  signs in through the real login form against live production with a dedicated
  test account, sourced from Infisical or a gitignored `.env.e2e-prod` fallback.
  Deliberately kept out of CI (every run authenticates a real account against a
  live system). `guardian-admin-smoke.spec.ts` is a regression guard for the
  admin-only-account crash fixed by #236, walking `/guardian`,
  `/guardian/intake`, `/guardian/requests`, and `/guardian/profiles`.

### Fixed
- Production `story_request` table was missing 7 columns
  (`initiator_role`, `age_band`, `length`, `narrative_style`, `series_id`,
  `anchor_storybook_id`, `proposed_series_title`) that the baseline schema
  declares: the baseline migration was recorded as applied in
  `supabase_migrations.schema_migrations` but never actually ran these
  changes against the live database, causing `GET /v1/story-requests` and
  `GET /v1/admin/story-requests` to 500 with
  `asyncpg.exceptions.UndefinedColumnError`.
  `supabase/migrations/20260713173427_add_story_request_metadata_columns.sql`
  backfills the missing columns and constraints, guarded to be a no-op
  wherever the baseline already applied them cleanly (CI, a fresh dev
  clone, staging) as well as on production, where it does the real work.

## [0.2.0] - 2026-07-12

### Added
- Dual admin/guardian roles (#236; see
  `docs/planning/admin-guardian-dual-roles-plan.md`). `User.role` stays the
  single base persona (`guardian`/`child`/`admin`); a new orthogonal
  `is_admin` boolean capability column lets one adult be a guardian, an
  admin-only reviewer, or both (`role='guardian', is_admin=true`).
  `supabase/migrations/20260712000000_user_is_admin.sql` adds the column
  (`NOT NULL DEFAULT false`, backfilling `is_admin=true` for existing
  `role='admin'` rows) plus a `ck_user_child_not_admin` CHECK constraint that
  keeps the capability off child rows; `db/models.py::User` carries the
  identical CHECK in its ORM `__table_args__`. `api/deps.py::Principal`
  derives `is_admin=true` for the `admin` base role in `__post_init__`
  regardless of the stored flag (so a legacy admin-only row never loses the
  capability) and force-clears it for `child` (defense in depth behind the DB
  CHECK). A new `Principal.acting_role(target_family_id)` method decides which
  role an audit stamp records: the base role for an action within the
  principal's own family, and `admin` for a dual-role adult acting on another
  family, since only the admin capability can authorize that cross-family
  write. Story-request creation, approval, and decline all stamp through
  `acting_role()`, so a dual-role adult's cross-family actions are
  attributable in the append-only pipeline event log as `admin`, not the
  guardian base persona, while the same adult's own-family actions are
  stamped with their base role. `GET /api/v1/story-requests` is now
  family-scoped for every caller (guardian, admin, and child alike, with an
  added child-profile narrowing so a child only ever sees their own profile's
  requests); the admin base role previously could not list requests at all. A
  new `GET /api/v1/admin/story-requests` endpoint adds a global,
  cross-family queue restricted to the admin capability. `GET /v1/me` now
  returns `is_admin` alongside `role`, so the frontend can branch on the
  capability independent of the base persona
  (`frontend/src/auth/types.ts::Principal.isAdmin`).
- Parallel `/admin/*` frontend console (`frontend/src/admin/`), a companion
  adult surface to the existing `/guardian/*` console for admin-capability
  functions: an admin review queue (`AdminConsolePage`), the cross-family
  request queue (`AdminRequestsPage`, with a family selector since it spans
  families), review detail, and the moderation dashboard/thresholds pages
  (relocated here from the guardian subtree). Gated on the `is_admin`
  capability, not the base role, via `ProtectedRoute`, so a dual-role adult
  reaches both `/guardian` and `/admin` from one login and the two shells
  cross-link for it; a plain guardian who navigates to `/admin` is redirected
  back to the guardian console rather than looping to the login page. The
  admin console carries its own `ParentalGate` (P6-08) instance around every
  surface, including the cross-family request queue: the admin capability
  alone proves the adult HAS admin rights, not that a grown-up is holding the
  device right now, and the request queue renders other families' child
  request text, so it needed the same re-auth challenge as approval/review.
- Guardian 401 retry-with-refresh (P6-06): when a request that carried the
  guardian bearer gets a 401 (typically an access token that expired before
  supabase-js's background refresh caught it), `useApi`'s response
  interceptor now calls `supabase.auth.refreshSession()` once, writes the
  new access token to `localStorage['auth_token']` (an idempotent
  write-through; `AuthContext`'s `TOKEN_REFRESHED` handler later stores the
  same value), and retries the original request exactly once with the fresh
  token. Concurrent 401s from parallel requests share a single in-flight
  refresh promise (Supabase rotates refresh tokens on use, so racing
  parallel refreshes could invalidate each other), and retried requests
  carry a one-shot config marker so a second 401 falls through to the
  pre-existing failure path (clear token, redirect off guardian paths)
  instead of looping. The Supabase client is loaded via dynamic import so
  the kid bundle still omits it entirely. Child-token 401s are deliberately
  untouched: child session tokens are not refreshable by design (fixed TTL;
  expiry means hand the device back to a grown-up), so they keep the
  existing clear-session-and-gate behavior, and 401s on requests that
  carried no bearer at all are also unchanged. The refresh is bounded by a
  client-side deadline, cannot run from a kid-token route (it never imports
  the Supabase client on the kid surface), and a refresh whose write-through
  to `localStorage` fails opens a short cooldown so a locked-down browser
  cannot drive a refresh-token-rotation storm.
- `scripts/backfill_covers_r2.py`: one-shot operator script that migrates
  pre-R2 cover art from Supabase Storage to Cloudflare R2 (#214), closing the
  gap the R2 cutover PR (#209) explicitly left open ("this PR does not
  backfill or re-upload them to R2, so old covers keep loading from Supabase
  until a future backfill"). Selects every `storybook_version` row with a
  non-null `cover_image_url`, classifies each as `"r2"` (already migrated via
  a `startswith(settings.r2_public_base_url)` check; skipped, not a
  candidate), `"supabase"` (matches the pre-R2 public-URL shape
  `https://<project-ref>.supabase.co/storage/v1/object/public/<bucket>/<key>`,
  tolerating an optional `?...` cache-busting suffix; a migration candidate),
  or `"other"` (skipped). Each candidate is downloaded, re-uploaded to R2 via
  the existing `covers.storage.upload_cover()` under the same
  `{storybook_id}/{version}.webp` key the live generation path uses, then
  downloaded back from the new R2 URL and compared byte-for-byte against the
  original before the database row is touched at all; a mismatch, or any
  download/upload exception, leaves the row untouched and counts it as
  failed rather than risking a half-migrated or corrupted cover. Supports
  `--dry-run` to log candidates and print a summary without writing
  anything. Uses a browser-like User-Agent on both downloads: the
  williamshome.family Cloudflare zone's bot protection returns 403 for the
  default python-httpx User-Agent, which was observed in practice during the
  PR #209/#210 R2 rollout smoke tests. Idempotent: re-running against an
  already-migrated row is a no-op (classified `"r2"`, not a candidate).
- Hybrid post-quantum cryptography readiness (ADR-013). The JWT
  signature-algorithm allowlist in `api/deps.py` is now configuration
  (`Settings.oidc_allowed_algs`, env `OIDC_ALLOWED_ALGS`, default
  `["RS256", "ES256"]`) instead of a hardcoded list, so a future
  post-quantum JOSE algorithm (e.g. ML-DSA) is an env change, not a code
  change; a startup validator refuses an empty list, `none`, and the
  symmetric `HS*` family so the new knob cannot reopen the alg=none or
  HS256-confusion forgeries. `scripts/check_fips_compatibility.py` now
  recognizes the finalized FIPS 203/204/205 algorithm names (ML-KEM,
  ML-DSA, SLH-DSA, and the hybrid `X25519MLKEM768` TLS group) as approved
  and warns on pre-standardization names (Kyber, Dilithium, SPHINCS+) with
  migration hints. An explicit `cryptography>=45` floor (the ML-DSA/SLH-DSA
  primitives) is pinned in `pyproject.toml`, and a living cryptographic
  inventory ships at `docs/security/crypto-inventory.md`. Key-exchange
  enablement (hybrid X25519+ML-KEM on the ingress legs) is owned by the
  `homelab-infra` repo per the ADR; nothing in this repo pins TLS groups.
- Cross-repo image-build trigger (`.github/workflows/trigger-image-build.yml`):
  every push to `main` that touches image content now fires a
  `repository_dispatch` (event type `cyo-adventure-push`, pushed commit SHA in
  `client_payload.ref`) at `ByronWilliamsCPA/homelab-infra`, whose
  `cyo-adventure-build.yml` (receiver trigger live on its main since
  homelab-infra#591 merged) rebuilds and publishes the backend/frontend
  images from exactly that commit. GitHub accepts a dispatch (204) even
  with no listener, so the receiver's weekly schedule remains the backstop
  if that trigger ever drifts. Previously images were only built on manual dispatch or a
  weekly schedule, so merges could sit unpublished for days while the live
  deploy served a stale build. Doc-only paths (`docs/**`, `**.md`,
  `.claude/**`, `mkdocs.yml`) are ignored. Requires the
  `HOMELAB_INFRA_DISPATCH_TOKEN` repo secret (fine-grained PAT, Contents
  read/write on homelab-infra, the permission that
  `POST /repos/{owner}/{repo}/dispatches` requires; Actions permissions are
  not sufficient); a missing/empty secret fails the run via an
  explicit guard step, and an invalid/expired token fails the `gh` call
  loudly (HTTP 401) rather than silently skipping the dispatch.

### Security
- Enabled Row Level Security (RLS) on all 19 public tables as defense-in-depth
  against the Supabase PostgREST anon/authenticated path (issue #125). The
  FastAPI backend connects via the session pooler as the `postgres` role,
  which Postgres always exempts from RLS, so app behavior is unaffected; the
  exposure closed is that, with RLS off, anyone holding the project's anon
  key could read or write every public table (including `child_profile`)
  directly through PostgREST. No policies are added: this is deny-by-default
  for anon/authenticated, since no client in this project uses PostgREST
  (the frontend's `@supabase/supabase-js` client is Auth/GoTrue only:
  `auth.getSession`, `auth.onAuthStateChange`, `auth.signInWithOAuth`,
  `auth.signInWithPassword`, `auth.signOut`; a repo-wide grep of
  `frontend/src/` found no `supabase.from(` or `supabase.rpc(` PostgREST
  table access). `FORCE ROW
  LEVEL SECURITY` is deliberately not used: the tables are owned by
  `postgres`, and forcing RLS with zero policies would also lock out the
  table owner, i.e. the application itself. See
  `supabase/migrations/20260711200745_enable_rls_all_tables.sql`.

### Changed
- CI: `ci.yml` opts into the org reusable workflow's new `parallel-tests`
  input (`ByronWilliamsCPA/.github` [#269](https://github.com/ByronWilliamsCPA/.github/pull/269)),
  splitting the unit/integration/security pytest buckets out of one
  sequential job into three parallel jobs plus a coverage-combine job. The
  ~5.5 min integration suite no longer sits behind unit and security on the
  critical path. No behavior change beyond CI wall-clock time: the same
  `coverage-reports` artifact this repo's `coverage-upload` job already
  consumes is produced under the same name and layout.
- Cover-art storage backend pivoted from Supabase Storage to Cloudflare R2
  (`covers/storage.py`). `upload_cover()` now uses `boto3`'s S3-compatible
  client against R2's endpoint (`https://{account_id}.r2.cloudflarestorage.com`)
  instead of an `httpx` POST to the Supabase Storage REST API; the blocking
  boto3 call runs inside `asyncio.to_thread` to stay off the event loop.
  `boto3` was chosen over a hand-rolled SigV4 signer (security-sensitive: use
  a vetted library) and over lighter alternatives like `minio` because
  `boto3-stubs[s3]` gives complete, already-published type stubs that pass
  BasedPyright strict mode with no custom typing shims. New settings
  (`core/config.py`): `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` (default unchanged: `"covers"`,
  replacing the old `covers_bucket` field), and `R2_PUBLIC_BASE_URL` (the
  Cloudflare custom domain connected to the bucket; covers are served to
  browsers from that domain, not from the S3-compatible endpoint, which is
  not publicly reachable). S3 `PutObject` is inherently an upsert, so the
  re-roll-overwrites-prior-cover behavior at a given
  `{storybook_id}/{version}.webp` key is unchanged. The stale `#CRITICAL`
  comment about Supabase Storage's 500MB total cap is replaced with R2's
  free-tier 10GB cap. The now-fully-dead `supabase_url` /
  `supabase_service_key` settings fields are removed: a repo-wide grep found
  no reader of them outside the covers module (the same-named
  `SUPABASE_URL` env var read directly by `scripts/seed_staging.py` for the
  Supabase Auth admin API is a separate, unrelated env lookup and is
  untouched). `api/covers.py`'s pre-enqueue config guard now checks the four
  R2 settings instead of the two Supabase ones.
  **No migration**: covers already generated and stored in Supabase Storage
  keep their existing Supabase public URLs in `storybook_version.cover_image_url`;
  this PR does not backfill or re-upload them to R2, so old covers keep
  loading from Supabase until a future backfill (not scoped here) moves them.
- Guardian console visual refresh (C1+C2): the shell chrome from the C0
  design-direction spike is now the permanent implementation, with an
  explicit sticky-chrome z-index ladder (header above the review action
  bar) and a muted "Guardian"/"Admin" role hint beside the brand title.
  Five card families (console feed, profiles, intake requests, review
  findings, books), four form-field stacks, and the error/muted text
  styles are consolidated onto shared `:is()` rules in
  `frontend/src/guardian/guardian.css`, backed by two new design tokens
  (`--color-border-soft`, `--surface-raised`) in
  `frontend/design-system/src/tokens.css`. `ModerationDashboardPage` and
  `ModerationThresholdsPage` now get contextual table styling
  (parchment-dark header, hairline row separators) without any density
  change. No class was renamed; `GuardianShell.test.tsx` gains role-hint
  coverage, and no other test file was touched.

### Fixed
- Two-phase release pipeline hardening (follow-up to #227, which merged before
  its review fixes landed): a failed auto-merge enable on the release PR now
  fails the job hard instead of emitting a swallowed warning, so a stalled
  release surfaces immediately; the `propose` job is pinned to `refs/heads/main`
  so a prerelease `workflow_dispatch` from another branch cannot break the tag
  and CHANGELOG contract; the semver guard now matches the whole computed
  version in bash (the previous piped `grep` anchored per line and accepted
  `1.2.3.4`); the bump commit is skipped cleanly when a re-run has nothing to
  commit; `promote_changelog.py` inserts the version heading line-anchored and
  `extract_changelog_section.py` is fenced-code aware, so a `## [` string in
  prose or inside a code block can no longer misplace the insertion or truncate
  the release notes; and the release scripts gained a smoke test over the real
  `CHANGELOG.md`.
- Design-system library build (Vite 8/rolldown): `react/jsx-runtime` is now
  externalized in `frontend/design-system/vite.config.ts`. Rolldown otherwise
  inlines the jsx runtime with a CJS-interop shim whose runtime
  `require("react")` throws in browser consumers of the ESM dist.
- Release pipeline reworked to be branch-ruleset compatible (#157; closes #183
  and #158). `release.yml` no longer pushes a version bump directly to `main`
  (rejected with GH013 by the `pull_request`, `required_signatures`, and
  `merge_queue` rulesets); it now runs a two-phase flow. Phase 1 (`propose`):
  on push to `main` (or manual dispatch), python-semantic-release is used
  purely as a version calculator (`semantic-release version --print`; it
  never writes files or tags), then `uv version` bumps `pyproject.toml`,
  `uv lock` refreshes the embedded version, and the new
  `scripts/promote_changelog.py` promotes the hand-curated `[Unreleased]`
  CHANGELOG section to the release version. The changes go up as a
  `release/vX.Y.Z` PR with auto-merge enabled, so the bump lands through the
  merge queue like any other change. Phase 2 (`publish`): when that
  `chore(release):` commit merges, the workflow tags `vX.Y.Z` and creates a
  GitHub Release whose notes come from the new
  `scripts/extract_changelog_section.py` (idempotent; safe on re-runs).
  The propose job authenticates with a `RELEASE_TOKEN` fine-grained PAT
  (contents + pull-requests write) because `GITHUB_TOKEN`-created PRs do not
  trigger the required CI workflows; the job fails with an actionable message
  if the secret is missing. `publish-pypi.yml` is deleted (#158): this is a
  deployed application, not a distributable package, and the workflow would
  have attempted a real PyPI upload on every GitHub Release.
- WCAG AA contrast sweep on the guardian console: every remaining
  resting-state (non-hover) use of the bright amber token as a border or
  text color moved to the contrast-safe `--color-amber-deep`, including
  `.intake-chip`, `.intake-chip--on`, `.intake-request__assign`, and
  `FlagBadge`'s "flag" tone (now a solid amber-deep fill with ink text
  rather than amber-deep text on a light tint, which could not clear
  4.5:1 at a badge's fixed size). One named exception:
  `.review-node--flagged`'s decorative border-left stripe deliberately
  stays bright amber, since it is a non-text accent and the flagged state
  is redundantly conveyed by the adjacent FlagBadge text, so WCAG 1.4.11
  is already satisfied without changing this element.
  `.books__row` / `.books__assigned` and
  `.assign__content-summary` no longer fall back to nonexistent
  `--color-border` / `--color-text-muted` tokens (a silent cold-gray
  render), and now use the new `--color-border-soft` / `--color-ink-muted`
  tokens.
- The kid surface no longer collapses every fetch failure into one generic
  retryable error: the profile picker (`/kids`) and library
  (`/library/:profileId`) now distinguish an unauthenticated session (an
  ask-a-grown-up gate linking to guardian sign-in, with no dead-end "Try
  again"), a forbidden response (a way back to the profile picker), transient
  failures (retry, now with an in-page route back to the picker), and the
  existing zero-items empty states. A 401 on a rating save surfaces the same
  gate instead of failing silently. Kid-surface fetch and rating logging is
  redacted through a shared `logApiError` helper to `{status, url}` only, so
  neither the Authorization header nor the response body can reach the console.
  The auth-gate states announce to assistive tech via `role="status"`. Covered
  by Vitest state tests, a `logApiError` redaction test, and a no-token
  Playwright scenario in the naive-user suite. Fixes #196 and the kid half of
  naive-UX finding F1 (#137).

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
- Optional per-profile PIN for the kid profile picker (P6-07, second half:
  the picker itself already existed). A guardian can set (4-8 digits), change,
  or remove a picker PIN per child profile from the guardian console's profile
  edit dialog; `PATCH /api/v1/profiles/{id}` gains a `pin` field with
  omitted-vs-null semantics matching `avatar` (a digit string sets or
  replaces, an explicit `null` removes, omitted leaves unchanged). The PIN is
  stored write-only as `child_profile.pin_hash` (new nullable column, Supabase
  migration `20260711233452_add_child_profile_pin_hash.sql`), encoded
  `pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>` by the new
  `core/pin.py` (stdlib `hashlib.pbkdf2_hmac("sha256", ...)`, 600k iterations
  stored per hash so the default can be raised without invalidating rows, a
  per-profile random salt via `secrets.token_bytes`, and constant-time
  verification via `hmac.compare_digest`; FIPS-safe by construction, no
  bcrypt/md5). No API response ever contains the hash: profile views expose a
  derived `has_pin` bool only, and an integration test asserts on the raw
  response JSON. `POST /api/v1/child-sessions` is PIN-gated: when the target
  profile has a `pin_hash`, the body must carry the correct `pin` or the mint
  fails 403 with the distinct, kid-safe `PIN_MISMATCH` code (admins are
  checked too; a PIN-less profile ignores any supplied `pin`, so existing
  behavior is unchanged). This is a convenience lock behind an
  already-authenticated guardian token, not a security boundary, so no
  endpoint-local rate limiting was added (the app-wide
  `RateLimitMiddleware` applies). On the kid picker, choosing a
  `has_pin` profile now shows a kid-friendly numeric PIN prompt
  (`type=password`, `inputMode=numeric`, `autoComplete=off`; the typed PIN
  lives only in transient component state and is never persisted) before the
  child session is minted; a wrong PIN keeps the child on a gentle
  try-again message and deliberately does NOT navigate (navigating would
  fall back to the guardian token and bypass the lock), and never shows the
  ask-a-grown-up gate. The generated API client was regenerated from the
  updated OpenAPI schema.
- Parental gate on the guardian console's sensitive surfaces (P6-08), the gate
  pattern Apple expects in Kids Category apps. A new `ParentalGate` component
  (`frontend/src/auth/ParentalGate.tsx`) wraps, as a pathless layout route
  inside the existing `ProtectedRoute`, the console review queue (`/guardian`),
  review/approve detail (`/guardian/review/:id`), books/assignments
  (`/guardian/books`), profile management (`/guardian/profiles`), and the
  admin moderation pages (`/guardian/moderation-thresholds`,
  `/guardian/moderation-dashboard`); future purchase routes (P8-06) join the
  same group. When the gate is cold it renders a guardian re-auth challenge
  (password re-entry via the existing Supabase client's `signInWithPassword`
  against the current session user's email) instead of the wrapped page; a
  correct password warms the gate for a 5-minute TTL held in module memory
  only (`frontend/src/auth/parentalGateState.ts`, keyed by Supabase user id;
  never `localStorage`, so a reload or new tab always re-challenges), a wrong
  password shows an inline error and stays locked, and cancel navigates back.
  Intake (`/guardian/intake`) and the request list (`/guardian/requests`)
  deliberately stay outside the gate: viewing and asking are not the
  high-stakes actions; approving, assigning, and settings are. Kid routes have
  zero interaction with the gate (it ships in the guardian lazy chunk only).
  A guardian who signed in via OAuth has no password to re-enter and
  supabase-js offers no client-side OAuth re-auth challenge, so OAuth users
  pass through with a console-visible warning rather than being locked out of
  approval; a real challenge for them (gate PIN or backend re-auth grant) is
  follow-up work. **Deferred, deliberately**: the plan's companion
  "approval freshness guard" backend note (a bounded `auth_time`/`iat`
  recency check on the approve endpoint) is not implemented because it is not
  sound with Supabase sessions; the client's silent token refresh also mints
  a fresh `iat`, so an `iat`-recency check cannot distinguish a
  re-authenticated human from a walked-away auto-refreshing session.
  Server-side freshness needs its own attestation design (candidate: a
  backend-minted, short-lived re-auth grant demanded by the approve
  endpoint), tracked as future work. Covered by a 12-case Vitest suite
  (`ParentalGate.test.tsx`: cold challenge, unlock, wrong password,
  connection failure, warm mount, cross-user warm entry, TTL expiry under
  fake timers, OAuth pass-through, cancel, no-session fail-closed, no
  storage persistence, in-flight lock) plus router-level tests that the cold
  gate blocks the console, intake stays ungated, and the kid surface never
  mounts the gate.
- JIT guardian provisioning (P6-03): new endpoint `POST /api/v1/onboarding`
  (`api/onboarding.py`, wired in `app.py`). A guardian's first authenticated
  call creates their `Family` plus a guardian `User` row keyed on the verified
  Supabase `sub` and returns 201; every later call is idempotent, returning
  the existing `{family_id, user_id, role, created: false}` with 200. This is
  the only endpoint that accepts a fully verified token whose subject has no
  `User` row yet: a new `require_onboarding_identity` dependency in
  `api/deps.py` verifies the token through the same shared OIDC decode path
  (`_decode_oidc_payload`, factored out of and now also backing
  `_verify_oidc_jwt`) and additionally extracts the optional `email` claim;
  `require_principal` and every other endpoint keep rejecting unknown
  subjects with 401 exactly as before. A child session token (child audience)
  is refused with 403: a reading credential can never provision a guardian
  account. Admin and guardian are disjoint roles (an admin holds no family
  membership and resolves to an empty profile set), and onboarding cannot
  tell an intended admin apart from a guardian: a seeded admin resolves to
  its existing row and is returned unchanged (no family is created), so
  admin accounts must be seeded before their first sign-in. Two racing
  first-login requests are resolved via the repo's savepoint-retry pattern
  (both inserts inside `begin_nested()`; on the `ix_user_authn_subject`
  `IntegrityError` the savepoint unwinds and the loser re-reads and returns
  the winner's row, never a 500). The request body carries only a
  consent-capture seam (`OnboardingConsent`, accepted but not recorded;
  `_record_consent` is the documented no-op hook P7-02 fills). Schema: new
  nullable `email` varchar(320) contact column on `public."user"`
  (`supabase/migrations/20260711204606_add_user_email.sql` plus the ORM
  column in `db/models.py`), populated from the Supabase user's email claim
  when present (it may be an Apple relay address) and NEVER used as an
  identity key; `authn_subject` remains the sole key. The generated frontend
  client (`frontend/src/client/`) is regenerated for the new contract.
- Cross-tenant IDOR extension (P6-10): the authorization suite's two-family
  fixture (`tests/integration/conftest.py::seed`, family A and B) is now
  joined by a third, completely unrelated `stranger` fixture (family C, no
  shared storybook, assignment, story request, or profile with A or B), so a
  query that happens to reject only the one other family the suite knew
  about (rather than correctly checking "belongs to the caller's family")
  can no longer pass unnoticed. `test_authz_matrix.py` gains stranger-family
  parametrized checks in both directions (family C's guardian/child tokens
  against family A's resources, and family A's child token against family
  C's profile) across every ownership-scoped route already covered for
  family B, plus a leak-by-inclusion check on `GET /api/v1/profiles` (the
  response body's id set, not just the status code, is asserted to exclude
  both other families). `test_child_sessions.py` extends the same coverage
  to the real, backend-signed child-session JWT mint/verify path (G1/P6-04):
  a guardian cannot mint a session for a stranger family's profile in either
  direction, and a minted third-family token is proven to fail against
  family A's library/guardian routes and vice versa, closing the gap left by
  testing only the dev-stub role tokens. `test_guardian_books_api.py` adds
  the same third-family isolation and assignment-leak checks the file
  already ran against family B. No cross-tenant leak was found; every new
  check landed green against the existing implementation.
- Child-scoped session tokens for the kid surface (G1 / P6-04). A guardian (or
  admin) exchanges a child profile id for a short-lived, backend-signed HS256
  JWT scoped to `role=child` and that single `profile_id`; the kid surface uses
  it as its own bearer. Children are deliberately NOT Supabase users (ADR-009
  keeps guardians on Supabase): this is a distinct, self-contained credential.
  New endpoint `POST /api/v1/child-sessions` (guardian-or-admin only; a child
  token is refused at the role gate, a cross-family guardian at the ownership
  check) returns `{token, expires_at, profile_id}`. `require_principal` gains a
  second verification branch (`core/child_session.py`): it routes on the token's
  unverified `aud` claim, but each branch then fully verifies its own family of
  token, the child branch pinning `algorithms=["HS256"]` plus a fixed, distinct
  issuer/audience (`cyo-adventure` / `cyo-child-session`) against
  `CHILD_SESSION_SECRET`, so a token can only ever verify through the branch that
  minted it (no `alg=none` forgery and no RS256/HS256 confusion in either
  direction). The child `User.id` is embedded at mint so the resulting principal
  is attributable on the append-only pipeline event log without a database read,
  keeping verification offline-friendly. Because profiles created through
  `POST /api/v1/profiles` get no `User` row (only the seed scripts ever created
  child accounts), the mint endpoint JIT-provisions the child account when it
  is absent: a `role="child"` `User` row with a deterministic synthetic subject
  (`child-profile:{profile_id}`, which cannot collide with a Supabase UUID sub
  or the seed scripts' opaque subjects), created inside the same unit of work
  under the family authorization that already ran. A concurrent double-mint
  from two guardian devices converges on one row: both compute the same
  subject, the loser's INSERT hits the unique `authn_subject` index inside a
  savepoint (the `begin_nested` pattern from `generation/series_link.py`), and
  it recovers by reading the winner's committed row. New settings
  (`core/config.py`):
  `CHILD_SESSION_SECRET` (required outside `local`, validated at startup) and
  `CHILD_SESSION_TTL_SECONDS` (default 43200, a 12h offline reading session,
  since a child session cannot be refreshed). The dev-stub token path is
  unchanged and remains local-only.

  **Frontend half (G1)**: the kid surface now runs on the minted child token
  instead of the guardian's own bearer. `ProfilePickerPage` mints a session
  (`frontend/src/kid/childSessionApi.ts`, a hand-typed adapter over the
  generated `ChildSessionCreateBody`/`ChildSessionView` types) with the
  guardian's bearer right after a profile tile is picked, stores
  `{token, expiresAt, profileId}` in `localStorage`
  (`frontend/src/auth/childSession.ts`), then navigates into
  `/library/:profileId` regardless of whether the mint succeeded (a failed
  mint falls back to the pre-G1 behavior of the guardian token, if any, so a
  transient mint failure never traps a child on the picker). Token selection
  lives centrally in `useApi.ts`'s request interceptor: on a kid-token route
  (`/library/*`, `/read/*`) it attaches a still-valid child token instead of
  the guardian bearer, and never attaches both; `/kids` itself is
  deliberately EXCLUDED from "kid-token route" even though it is
  kid-facing, because the picker's own profile listing and mint call need
  the guardian's full-family scope, and `KidNav`'s "Switch reader" link
  returns to `/kids` without clearing anything, so a lingering child token
  there would silently narrow the picker to one profile. The response
  interceptor determines which bearer a failing request actually carried
  (by comparing its `Authorization` header to the stored child token, not by
  route) before clearing anything, so a dead child token never tears down a
  live guardian session and vice versa; a kid-route 401 clears the child
  session and relies on the existing ask-a-grown-up gate
  (`classifyApiError`'s `unauthenticated` state in `ProfilePickerPage` and
  `LibraryPage`) to recover, with no new error UI. An expired child token is
  also caught client-side (`isExpired`/`getValidChildSession`) before ever
  being attached, as a courtesy on top of the server's own `exp`
  verification. `AuthContext.tsx`'s `safeRemoveToken()` now also clears the
  child session, so guardian sign-out (or a guardian session that never
  resolves to a principal) ends a shared-device child session too. Out of
  scope for this slice (tracked separately): per-profile PIN (P6-07), a
  parental-gate re-auth wrapper (P6-08), Keychain/secure storage for the
  child token (P8-02), and pre-checking token expiry before an offline sync
  attempt (P6-06).
- Guardian console patterns promoted into `@cyo/design-system`: new `Card`,
  `FormField`, and `Chip` primitives (with `.cyo-text-error` / `.cyo-text-muted`
  text-tone utilities, consuming the pre-existing amber token pair:
  `--color-amber` stays the bright brand hue, `--color-amber-deep` is the
  deeper shade that clears the 3:1 WCAG non-text/large-text threshold,
  though not the 4.5:1 AA normal-text minimum), and the guardian console
  now consumes them instead of its bespoke `guardian.css` equivalents (the
  `.intake-chip` styles, orphaned by this same swap, are removed).
  `FlagBadge` deliberately stays bespoke: its flag/info tones belong to the
  moderation-review surface, which this promotion pass excluded.
- Auth-gate scenario tier for the `naive-ux-check` skill (issue #204): three
  new Track B comprehension scenarios (`K0` fresh-device kid gate, `G0`
  guardian sign-in discovery, `A0` admin sign-in signal) grow the prompt set
  from 14 to 17 and give the differentiated kid auth gates shipped in PR
  #198 their first naive-user verification (a clear, friendly, working gate
  now scores as a pass for these three scenarios). The skill's default
  target changes from plain local dev to local dev pointed at the seeded
  Supabase staging project via `.env.staging`, with live production demoted
  to an explicit, deliberate operator choice (mutating personas still never
  target it). `K1`-`K4` gain a documented operator precondition (sign in as
  the seeded test guardian, `SEED_GUARDIAN_EMAIL`, first), zero-state
  scenario premises are annotated for the seeded "Test Reader" fixtures,
  and stale pre-#206/#209/#210 UI descriptions in the prompt files were
  re-verified against the current frontend. Spec:
  `docs/superpowers/specs/2026-07-10-naive-ux-check-scenario-redesign-design.md`.
- Illustrated avatar set (issue #65 phase 1, "Bucket B"): the profile picker's
  8 emoji glyphs are replaced by 22 illustrated WebP presets (256x256,
  quality 80, 3.8-8.9KB each, ~134KB total), 14 of them new. The original 8
  preset ids (`fox` through `frog`) are unchanged so existing
  `ChildProfile.avatar` values are not orphaned. `avatarGlyph()` is renamed
  to `avatarSrc()` (`frontend/src/profiles/avatars.ts`), `AvatarCircle`
  renders an `<img alt="">` instead of a glyph span, and the offline
  precache (`vite.config.ts` workbox `globPatterns`) now includes `.webp` so
  avatars still render while offline. The unused, never-imported
  design-system copy of `AvatarCircle` (extracted from `frontend/src/profiles/`
  after C4a-2 but not wired into any consumer) is removed.
- Supabase multi-environment pipeline scaffold: CLI project config, baseline
  SQL migration squashed from the Alembic head, PR migration validation, and
  staging/production deploy workflows (staging auto on merge, production
  human-gated) (#199)
- Staging environment template (`.env.staging.example`) and an idempotent
  staging seed script (`scripts/seed_staging.py`) that creates disposable
  Supabase Auth test accounts (guardian, admin), a Test Family, and an
  age-band 5-8 child profile with two published fixture stories, guarded so
  it refuses to run unless `ENVIRONMENT=staging` (#205)
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
  applies the migration chain and seeds dev data before newman runs; pacing is
  supplied by newman's `--delay-request` rather than an in-collection
  busy-wait; the suite and its local run loop are documented in
  `docs/api/README.md`.

### Changed
- Schema migrations moved from Alembic to Supabase CLI SQL migrations
  (ADR-012): baseline squash, forward-only policy, schema-parity CI gate.
  The provider/model allowlist rows the retired Alembic migration seeded are
  now seeded idempotently by `scripts/seed_dev_data.py`, so an environment
  built from the schema-only baseline can still generate stories (#201)

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

[Unreleased]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.25.0...HEAD
[0.25.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.24.0...v0.25.0
[0.24.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.23.0...v0.24.0
[0.23.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.22.1...v0.23.0
[0.22.1]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.22.0...v0.22.1
[0.22.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.21.0...v0.22.0
[0.21.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.20.0...v0.21.0
[0.20.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.19.0...v0.20.0
[0.19.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.18.4...v0.19.0
[0.18.4]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.18.3...v0.18.4
[0.18.3]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.18.2...v0.18.3
[0.18.2]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.18.1...v0.18.2
[0.18.1]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.18.0...v0.18.1
[0.18.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.17.0...v0.18.0
[0.17.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.12.1...v0.13.0
[0.12.1]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/releases/tag/v0.1.0
