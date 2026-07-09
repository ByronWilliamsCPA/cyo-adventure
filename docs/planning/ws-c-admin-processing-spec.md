---
schema_type: planning
title: "WS-C Spec: Admin Processing (per-request provider/model + cell-aware skeleton matching)"
description: "Workstream spec for WS-C: a DB-backed admin-editable provider/model allowlist, a
  per-job provider factory, the direct-Anthropic provider, and band/length/style auto-vary
  skeleton matching with an unconstrained admin override."
tags:
  - planning
  - project
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Define the ratified scope, data model, API surface, and delivery decomposition for
  WS-C so the implementation plan can be written against a single source of truth."
component: Strategy
source: "docs/planning/story-lifecycle-redesign.md (umbrella, ratified 2026-07-06), Design
  sections 2 and 4, ratified decision 5; WS-C handoff docs/planning/ws-c-handoff-2026-07-08.md;
  current-state verification against main @ d17ccce (2026-07-08)."
---

## Scope and non-goals

WS-C is the admin-processing workstream. It makes the admin authoring-plan step the explicit
processing gate for every request: the admin chooses the generation provider and model
(constrained by an allowlist), and the system auto-varies skeleton selection across the full
ADR-011 cell with an admin override. It depends only on WS-B (band/length/style already on the
request, merged in #164/#165/#167) and unblocks WS-G (series chaining).

In scope:

1. A DB-backed, admin-editable provider/model **allowlist** with an audit trail.
2. `build_provider()` becomes a **per-job factory** taking per-request overrides, falling back
   to global `Settings`. Mock stays for CI.
3. The deferred **direct-Anthropic provider** is implemented (canonical name `anthropic`).
4. Skeleton matching moves from band-only to the **full ADR-011 cell** (band x length x style;
   style collapses to prose below bands 13-16), auto-varied and **weighted against the
   family's recently used skeletons**, with an **unconstrained admin override**.
5. Authoring-plan request gains `provider`/`model`; the response shows the skeleton pick plus
   eligible alternatives.

Explicit non-goals (deferred to their own workstreams):

- No `pipeline_event` writes. The allowlist gets its own audit table now; the umbrella's
  eventual consolidation onto `pipeline_event` is WS-D's work (per the comment at
  `db/models.py:620-621`).
- No series chaining or generation-path changes (WS-G).
- No catalog visibility work (WS-E).
- No frontend UI beyond the mandatory regenerated API client. Building an admin allowlist
  editor screen is out of scope; the endpoints ship and the client is regenerated so a later
  UI can consume them.

## Ratified decisions (this workstream)

Decided by the owner during spec brainstorming, 2026-07-08. These are settled.

| # | Decision | Choice | Rationale |
| --- | --- | --- | --- |
| C-1 | PR decomposition | Two PRs: PR1 provider work, PR2 skeleton matching | Mirrors WS-B vertical slices; each PR independently reviewable |
| C-2 | Migration count | Two migrations, one per PR, linear chain | Each PR's schema is self-contained; accepted the marginally larger WS-D rebase |
| C-3 | Allowlist storage | DB-backed, admin-editable, full editor (list/add/enable/disable) + audit trail | Runtime control with attributable history; providers stay code-fixed, only model IDs are DB-managed |
| C-4 | Recency weighting | Inverse-frequency with a floor; deterministic RNG in tests; uniform fallback | Delivers "weighted against recently used" while guaranteeing variety and never starving a small cell |
| C-5 | Direct-Anthropic impl | Official `anthropic` SDK (AsyncAnthropic); canonical name `anthropic` everywhere | Owner preference; removes the existing claude-vs-anthropic naming split |
| C-6 | Skeleton override | Unconstrained: admin may override to any skeleton, including non-production-eligible | Maximum admin power; a warning surfaces when the pick is non-production or out-of-cell |

## Current-state anchors (verified against main @ d17ccce, 2026-07-08)

Two handoff claims were found **stale** and are corrected here so they do not propagate into
the plan:

- **Skeleton metadata already has `length` and `narrative_style`.** `StoryMetadata`
  (`storybook/models.py:207-234`) carries `length: Length | None` and
  `narrative_style: NarrativeStyle`, and all 18 production skeleton JSONs already set both.
  WS-C does **not** add a `length` field to skeleton metadata and does **not** backfill the
  library. It only changes *matching* to read those existing fields.
- `select_skeleton_for_band(band)` (`generation/skeleton_match.py:27`) is first-in-band
  alphabetical and style/length-blind; it cannot distinguish the three cells that share a
  band. This is the function WS-C replaces.

Confirmed integration points:

- `AuthoringPlanRequest` (`api/schemas.py:573-603`) has `method`/`mechanism`/`prep_model`/review
  models but no `provider`. Admin-only enforced at the endpoint (`api/story_requests.py:750`).
- `core/config.py:134-136` declares `generation_provider: Literal["mock","claude","ollama","openrouter","modal"]`;
  `build_provider(settings)` (`generation/provider.py:490`) raises `ConfigurationError` for
  `"claude"` (deferred). The `"claude"` path was never functional, so renaming it to
  `"anthropic"` breaks no working configuration.
- `GenerationProvider` Protocol (`provider.py:185`) requires exactly
  `async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str`; concrete
  providers also expose a `name` property and `model` attribute used for labeling.
- `persist_storybook`/`StorybookParams` (`generation/persistence.py:66,110-119`) is the single
  choke point creating `StorybookVersion` rows; `provider`/`model` are set there from worker
  values. `StorybookVersion` (`db/models.py:209-243`) has no `skeleton_slug` column yet.
- Migration head: `e1f2a3b4c5d6`
  (`20260708_1600_add_series_and_soft_continuation.py`), nothing chained onto it.

## Design

### PR1: provider work

#### Allowlist data model (mirror ModerationThreshold + its audit table)

New table `provider_model_allowlist`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | Uuid PK | `default=uuid.uuid4` |
| `provider` | String(32) | CHECK against the fixed provider set (`anthropic`, `openrouter`, `modal`, `ollama`); `mock` is never allowlisted (CI-only) |
| `model_id` | String(120) | the provider-native model id (e.g. `claude-sonnet-4-5`, `anthropic/claude-3.5-sonnet`) |
| `enabled` | bool | `default=True, server_default=true` |
| `display_name` | String(120) or null | optional human label for a future UI |
| `created_by` | Uuid null FK -> user.id | |
| `updated_by` | Uuid null FK -> user.id | |
| `created_at` / `updated_at` | timestamptz | `server_default=now()`, `updated_at onupdate=now()` |

Constraints: `UniqueConstraint(provider, model_id)`, `CHECK provider IN (...)`.

New append-only audit table `provider_model_allowlist_audit` (mirrors
`moderation_threshold_audit`, `db/models.py:617-670`):

| Column | Type | Notes |
| --- | --- | --- |
| `id` | Uuid PK | |
| `provider` / `model_id` | String | the affected entry's natural key |
| `action` | String(16) | CHECK in (`create`, `update`, `delete`) |
| `old_enabled` / `new_enabled` | bool or null | before/after |
| `changed_by` | Uuid **NOT NULL** FK -> user.id | every edit attributable (RAD: security) |
| `changed_at` | timestamptz | `server_default=now()` |

Audit rows are written **in the same unit-of-work** as the mutation (both commit or both roll
back), exactly as `api/moderation_thresholds.py:199-210` does.

**Seeding (differs from ModerationThreshold, which is a sparse no-seed override set):** an empty
allowlist means nothing is selectable, so PR1's migration **seeds** known-good rows, following
the seeded `ModerationSetting` migration pattern
(`20260707_1700_add_moderation_setting.py`): parameterized `op.execute(sa.text(...))` with
server-evaluated `now()`, no imports of live app constants (seed literals are hand-synced with
a `DEFAULT_ALLOWLIST` constant in code, referenced by the endpoint's re-seed/tests, and
documented as needing manual sync in the migration). Initial seed set (final list confirmed in
the plan): a small anthropic set, the current openrouter production + fallback models, and the
modal/ollama models already named in `Settings`.

`#CRITICAL: security: the allowlist is the control that keeps free-string model IDs out of
billing.` `#VERIFY: the authoring-plan endpoint rejects any (provider, model) that is not an
enabled allowlist row; providers themselves are a code-fixed enum so an admin cannot introduce
a new billing backend by typing a string.`

#### Allowlist admin endpoints (mirror api/moderation_thresholds.py)

Under `/api/v1/admin/provider-allowlist`, all guarded by `_require_admin(ctx)` first:

- `GET /admin/provider-allowlist` -> `AllowlistView` list (whole table, ordered by provider,
  model_id).
- `POST /admin/provider-allowlist` -> add a `(provider, model_id)` row (409 on duplicate,
  422 on unknown provider). Writes an audit row with `action="create"`.
- `PUT /admin/provider-allowlist/{id}` -> toggle `enabled` / update `display_name`. Writes an
  audit row with `action="update"`.
- `DELETE /admin/provider-allowlist/{id}` -> remove a row (404 if absent). Writes an audit row
  with `action="delete"` before deletion.

New Pydantic schemas in `api/schemas.py`: `AllowlistView`, `AllowlistListView`,
`AllowlistCreateBody`, `AllowlistUpdateBody`. Provider is validated against the fixed enum;
model_id is a stripped non-empty string.

#### Provider naming: canonical `anthropic`

- `core/config.py`: `generation_provider` literal becomes
  `["mock","anthropic","ollama","openrouter","modal"]` (rename `claude` -> `anthropic`). Add
  settings: `anthropic_api_key: SecretStr | None`, `anthropic_base_url` (default the SDK
  default), `anthropic_model` (default used when provider is anthropic globally and no per-job
  override is present). Reuse `llm_timeout_seconds` / `llm_effort`.
- `StorybookVersion.provider` provenance already stores `anthropic`, so this closes the split.

#### Direct-Anthropic provider (official SDK)

- Add the `anthropic` package as a runtime dependency (`uv add anthropic`), and update the
  lockfile, SBOM, and REUSE annotations. `#EDGE: external-resources: a new dependency adds a
  pip-audit / OSV surface.` `#VERIFY: run pip-audit and osv-scanner in the PR; document any
  finding per docs/known-vulnerabilities.md.`
- New `generation/providers/anthropic.py::AnthropicProvider`, structurally satisfying
  `GenerationProvider` (`async def complete(*, system, prompt, max_tokens) -> str`), exposing
  `name` (`f"anthropic:{model}"`) and `model`. It wraps `AsyncAnthropic`, mapping the SDK's
  error taxonomy onto the same transient-vs-leg-fatal `ProviderError` shape the
  `_base`/openrouter leg uses so retry behavior is consistent.
- `build_anthropic_leg(settings, model)` mirrors `build_openrouter_leg`: fails fast, by name
  only, when `ANTHROPIC_API_KEY` is absent (`#CRITICAL: security`), before any network call.

#### Per-job provider factory

- `build_provider` gains optional overrides:
  `build_provider(settings, *, provider_override: str | None = None, model_override: str | None = None)`.
  With no overrides it behaves exactly as today (back-compatible for every existing caller and
  test). A `"anthropic"` branch builds the new leg.
- The authoring-plan step records the admin's chosen `provider`/`model` into the job's
  `authoring_metadata` (the existing precedent: it already stores `review_stage1_model` /
  `review_stage2_model` there, `authoring_plan.py:191-192`).
- The worker builds the provider per job from that metadata. Because `build_provider` currently
  runs at `worker.py:690` *before* the job row loads, WS-C relocates provider construction to
  after `_load_and_start_job` (or reads the override off the already-loaded `job_row`),
  mirroring the existing per-job model override `_review_stage2_override` (worker.py:313-328,
  443). The injected-provider test path (explicit `provider` arg) is preserved and still wins.

`#CRITICAL: security: provider/model on the request are untrusted admin input.`
`#VERIFY: they are validated against the enabled allowlist at the authoring-plan endpoint
before they are ever persisted to authoring_metadata or reach a provider.`

#### Authoring-plan request additions (PR1 portion)

`AuthoringPlanRequest` gains `provider: str | None` and `model: str | None`. When `method` uses
a provider mechanism, both are required and validated as an enabled allowlist pair; `mock` is
not selectable. Validation failure raises `ValidationError` (422).

### PR2: cell-aware skeleton matching

#### `skeleton_slug` provenance column (PR2 migration)

Add `skeleton_slug: String(120) | None` to `StorybookVersion` (`db/models.py:209-243`), to
`StorybookParams` (`persistence.py:35-63`), and set it in `persist_storybook`
(`persistence.py:110-119`). The worker passes the slug it already has in
`job_row.authoring_metadata["skeleton_slug"]` through to `StorybookParams`. `null` for
fresh-generation and imported books.

#### Cell-aware selection with recency weighting

A new selection module replaces `select_skeleton_for_band`. It splits into a **pure, testable
core** and an **impure recency query**:

- Pure: `select_skeleton_for_cell(candidates, recent_usage, rng) -> Selection` where
  `candidates` is the list of production-eligible skeletons whose metadata matches the cell,
  `recent_usage` is a `{slug: count}` map, and `rng` is an injected `random.Random`. Weight for
  each candidate = `1 / (1 + recent_usage.get(slug, 0))` (inverse-frequency with an implicit
  nonzero floor, so nothing is ever fully excluded). Returns the weighted-random pick plus the
  full candidate list as `alternatives`.
- Cell definition: match `metadata.age_band == band` and `metadata.length == length`; for bands
  `13-16` and `16+` also match `metadata.narrative_style == style`; for lower bands the style
  axis collapses to prose and is not matched. Read via the typed `StoryMetadata`, not raw dict
  access (`#ASSUME: data-integrity` per the RAD note at `skeleton.py:64-70`).
- Impure: a query fetches `recent_usage` from `StorybookVersion.skeleton_slug` for the request's
  `family_id` over the most recent N versions (N a module constant, proposed 20; final value in
  the plan). When there is no family (`family_id` null for admin/catalog requests) or no
  history, `recent_usage` is empty and selection falls back to uniform-random over the cell.

`#ASSUME: data-integrity: length may be null on a request (nullable since #164).`
`#VERIFY: when request.length is null, define the fallback (proposed: treat as the band's
default length; resolved in the plan) so a cell can always be formed.`

#### Authoring-plan response + override (PR2 portion)

- `AuthoringPlanResponse` gains `skeleton_alternatives: list[AlternativeView]` (the in-cell
  production-eligible skeletons) alongside the existing `skeleton_slug` pick.
- `AuthoringPlanRequest` gains an optional `skeleton_slug` override. Override is **unconstrained**
  (C-6): any slug is accepted, including non-production-eligible and out-of-cell skeletons. When
  the override is non-production-eligible or outside the request's cell, a warning is attached to
  the response `warnings` list (the field already exists) so the mismatch is visible. An override
  naming a slug that does not exist on disk is a 422 (`ValidationError`), not a silent pass.

## Migration chain and WS-D coordination

- PR1 migration: `provider_model_allowlist` + `provider_model_allowlist_audit` + seed rows.
  `down_revision = "e1f2a3b4c5d6"`.
- PR2 migration: `skeleton_slug` on `storybook_version`. `down_revision =` PR1's revision.
- WS-D (sibling session) chains `pipeline_event` onto `e1f2a3b4c5d6` too. Whichever workstream
  merges second rebases and bumps its base migration's `down_revision` to the other's head. WS-C
  keeps a linear internal chain so its head is unambiguous.
- Shared files with WS-D (`story_requests/service.py`, `generation/worker.py`,
  `story_requests/authoring_plan.py`, `CHANGELOG.md`) will conflict on rebase; conflicts are
  mechanical. Transitions WS-C introduces (per-plan provider override) get evented by WS-D in a
  small follow-up after both merge, not coordinated mid-flight.

## Testing and delivery obligations

- **Migration tests** (`tests/integration/`) for both new revisions, pinning explicit revision
  ids (never `head`/`-1`), mirroring `test_moderation_threshold_migration.py` and
  `test_storybook_version_provider_migration.py`: chain assertion, upgrade/downgrade round-trip,
  tables/column present-only-while-upgraded, and seed-rows-present for PR1.
- **Unit tests**: allowlist validation + audit-row-written-in-same-transaction; `AnthropicProvider`
  error-taxonomy mapping and fail-fast-by-name; `build_provider` override behavior and back-compat;
  `select_skeleton_for_cell` weighting, floor, determinism under a seeded RNG, and uniform
  fallback; cell matching including the low-band style collapse.
- **Endpoint tests**: admin-only enforcement, allowlist CRUD, authoring-plan provider/model
  validation against the allowlist, skeleton alternatives in the response, and override warnings.
- **Coverage** stays >= 80%.
- **Client regen**: any schema/route change requires regenerating `frontend/src/client/` in the
  same PR via the in-process schema dump (`OPENAPI_INPUT=<file> npm run generate-client`, never
  sort keys) or the drift gate (ci.yml:200-247) fails. Both PRs touch schemas.
- **e2e**: update both `e2e/` and `e2e-real/` tiers for any flow change; the real tier is
  typecheck-only locally, disclosed in the PR body (established pattern, #164-#167).
- **Process**: signed commits, Conventional Commits, no em-dash, CHANGELOG entry or
  skip-changelog label, owner-gated merge (never auto-merge), merge queue only.

## Open items resolved during planning (not re-decided here)

- Final seed model list for the allowlist per provider.
- Recency window N (proposed 20).
- Request `length`-null fallback for cell formation (proposed: band default length).
- `AnthropicProvider` SDK error-to-`ProviderError` mapping table.
