# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Breaking (schema 2.0):** `Ending` now carries typed `valence` and `kind`
  instead of a free-form `type`; `StoryMetadata` requires `topology`. The
  exported JSON schema and the entire story/fixture corpus were migrated.

### Added
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
