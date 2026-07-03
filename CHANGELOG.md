# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Guardian concept-intake UI (C4a-5): a "Request a story" form that picks a
  child, captures a premise and tone, builds a full ConceptBrief from
  band-derived defaults, posts the concept, and enqueues generation. A
  persistent "My Requests" list polls while a request is generating and shows a
  status pill (Generating / Waiting for review / Approved / Failed) per request.
- `GET /api/v1/generation-jobs`: a guardian-only, family-scoped endpoint that
  lists a family's generation jobs newest-first with the linked storybook
  status, and never returns the raw generation report (ADR-007).

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
