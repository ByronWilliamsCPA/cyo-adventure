---
title: "CYO Adventure - Technical Specification"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Document the technical architecture and implementation details."
tags:
  - planning
  - architecture
component: Development-Tools
source: "Project Ariadne scoping handoff (architecture rev 3, 2026-06-20)"
---

# Technical Implementation Spec: CYO Adventure

> **Status**: Active
> **Version**: 1.1 | **Updated**: 2026-07-10
> **Codename**: Ariadne

## TL;DR

A React/TypeScript PWA reader plays a versioned JSON Storybook offline; a Python/FastAPI
backend serves the library, runs staged LLM generation behind a deterministic
validation-and-moderation gate, and enforces an admin approve-and-publish state machine. Postgres
holds metadata, reading state, and (at launch) the story blobs inline as JSONB; MinIO is
the deferred object-storage target for those blobs. Guardian identities authenticate via
Supabase OIDC, all deployable to the homelab behind Pangolin.

## Technology Stack

### Core

- **Language**: Python 3.12 backend; TypeScript frontend.
- **Package Manager**: uv (Python), npm (frontend).
- **Backend framework**: FastAPI + Pydantic v2.
- **Frontend framework**: React 19 + Vite.

### Code Quality

- **Linter**: Ruff (88 chars, PyStrict-aligned); ESLint + Prettier on the frontend.
- **Type Checker**: BasedPyright (strict).
- **Testing**: pytest, Hypothesis (Python); Vitest, fast-check, Playwright (frontend).

### Data Layer

- **Database**: PostgreSQL 16 + SQLAlchemy; schema migrations via Supabase CLI
  SQL migrations (ADR-012; Alembic retired). See
  [ADR-004](./adr/adr-004-homelab-first-deployment.md).
- **Story blob storage**: inline in Postgres JSONB (`storybook_version.blob`) at launch
  per [ADR-009](./adr/adr-009-supabase-platform.md). MinIO via the S3 API (Azure
  Blob interchangeable) is the deferred object-storage target for versioned, immutable
  story blobs; it does not hold them yet.
- **Cache / queue broker**: Redis.
- **Background work**: RQ (chosen over Celery for simplicity at this scale).

### Player and Offline

- **Player state**: XState (a story is a state machine; explicit transitions are
  testable). See [ADR-002](./adr/adr-002-client-pwa.md).
- **Offline**: service worker (Workbox via vite-plugin-pwa) + IndexedDB (`idb`).
- **Read-aloud**: Web Speech API (SpeechSynthesis), browser-native, Phase 4b.

### Generation and Safety

- **Condition logic**: in-house evaluator over the JSONLogic shape (Python +
  TypeScript). No third-party logic library. See
  [ADR-006](./adr/adr-006-conditions-inhouse-evaluator.md).
- **Graph analysis**: networkx (reachability, cycle, termination).
- **Readability**: textstat (Flesch-Kincaid grade, advisory).
- **LLM**: OpenRouter primary (reaching Claude models: `anthropic/claude-haiku-4.5`, with
  `anthropic/claude-sonnet-4.6` as the OpenRouter fallback), then local Ollama as the final
  fallback, behind a provider-agnostic interface. A `mock` provider is the default in CI.
  Direct Anthropic SDK access is deferred. See
  [ADR-003](./adr/adr-003-frontier-llm-generation.md) (amended 2026-06-22).
- **Moderation**: provider moderation API + an independent LLM-reviewer pass.

### Infrastructure

- **CI/CD**: centralized GitHub Actions.
- **Auth**: Supabase OIDC (guardian identities), guardian and child roles; provider-agnostic
  `oidc_*` config. See [ADR-009](./adr/adr-009-supabase-platform.md).
- **Ingress / orchestration**: Pangolin (zero-trust) + Docker + Dockge.
- **Observability**: Sentry + structured logging.

> Versions shown as "current major" are placeholders. Phase 0 produces a
> `TECHNICAL_BASELINE.md` pinning exact versions (React, Vite, TypeScript, XState,
> vite-plugin-pwa/Workbox, FastAPI, Pydantic, SQLAlchemy, Postgres, Redis,
> MinIO container tags, Node via `.nvmrc`). Container images are pinned by tag, never
> `latest`.

## Architecture

### Pattern

A modular monolith backend (FastAPI) with an asynchronous worker for generation, and a
single role-aware PWA client. At launch, story blobs, metadata, and state all live in
Postgres (blobs inline as JSONB); object storage is the deferred path for blobs. No
provider-specific services in the core.

### Component Diagram

```text
                         ┌──────────────────────────────────────────┐
                         │              Family devices               │
                         │   Kids (reader)      Parent (review)      │
                         └───────────────┬──────────────────────────┘
                                         │ HTTPS (Pangolin zero-trust)
                                         ▼
                         ┌──────────────────────────────────────────┐
                         │            PWA (React/TS/Vite)            │
                         │  Reader • Library • Review • Editor(P4b)  │
                         │  Service worker + IndexedDB (offline)     │
                         └───────────────┬──────────────────────────┘
                                         │ REST /api/v1 (OIDC via Supabase)
                                         ▼
        ┌────────────────────────────────────────────────────────────────────┐
        │                          FastAPI backend                           │
        │  Library API   Authoring API   Review API   Reading API            │
        │      │              │              │            │                  │
        │      ▼              ▼              ▼            ▼                  │
        │  Story catalog  Generation   Publish state   Progress store        │
        │                 orchestrator  machine                              │
        │                    │                                               │
        │     ┌──────────────┼───────────────────────┐                      │
        │     ▼              ▼                        ▼                      │
        │  Validator    Moderation             Provider interface           │
        │  (schema,     (API + LLM             (OpenRouter/                  │
        │  graph,       reviewer)              Ollama/mock)                  │
        │  state-space) │                            │                      │
        └───────────────┼────────────────────────────┼──────────────────────┘
                 │       │                            │
                 ▼       ▼                            ▼
          ┌───────────┐  ┌───────────┐         ┌──────────────┐
          │ Postgres  │  │   MinIO   │         │  LLM provider│
          │ metadata, │  │ (deferred │         │  (external/  │
          │ state,    │  │  blob     │         │   local)     │
          │ blobs +   │  │  target)  │         └──────────────┘
          │ raw gen   │  └───────────┘
          └───────────┘
                ▲
          ┌─────┴────┐
          │  Redis   │  background generation queue
          │ + worker │
          └──────────┘
```

### Component Responsibilities

| Component | Purpose | Key Functions |
|-----------|---------|---------------|
| PWA client | Play stories; host review and (P4b) editor | XState player, offline cache, role-aware UI |
| Library API | List and serve stories a child may see | Filter by published status, age band, reading cap; immutable version serving |
| Generation orchestrator | Drive staged passes | Structure, prose, repair; call provider and validator; write provenance |
| Validator | Prove the graph holds together | Schema, graph integrity, state-space, reading level, length (deterministic, no LLM) |
| Moderation | Independent safety signal | Provider moderation + LLM-reviewer; route risky passages to human review |
| Publish state machine | Enforce admin approval | No path to a child library without an admin approve-and-publish (`in_review -> published`); record approver and provenance |
| Reading store | Per-child progress | Current node, var state, path, save slots, completions; revision-based sync |

## Data Model

### Story format (the Storybook blob, stored inline in Postgres JSONB)

```text
Storybook
  - schema_version: String              # "2.0"; exactly one version is accepted
  - id: String                          # stable across versions
  - version: Integer                    # immutable once published
  - title: String
  - metadata:
      - age_band: Enum                  # "3-5" | "5-8" | "8-11" | "10-13" | "13-16" | "16+"
      - reading_level: { scheme, target, tolerance }
      - tier: Integer                   # 1 = branching, 2 = state-tracking
      - themes: [String]
      - estimated_minutes: Integer
      - ending_count: Integer
      - content_flags: { violence, scariness, peril }   # each an enum
  - variables: [Variable]               # empty for Tier 1
  - start_node: String                  # node id
  - nodes: [Node]

Variable
  - name: String                        # snake_case, declared once
  - type: Enum                          # "bool" | "int"
  - initial: any                        # type-consistent
  - min, max: Integer                   # for int, bounds the range
  - description: String

Node
  - id: String                          # unique within the story
  - body: String                        # passage prose (2nd person)
  - on_enter: [Effect]                  # state changes on arrival
  - choices: [Choice]                   # empty iff is_ending
  - is_ending: Boolean
  - ending: { id, valence, kind, title } # required iff is_ending; id is stable.
                                        # Two axes: valence (Valence enum) + kind (EndingKind enum)
  - tags: [String]

Choice
  - id: String                          # unique within the story (audit/debug)
  - label: String                       # choice text shown to the reader
  - target: String                      # an existing node id
  - condition: JSONLogic                # optional; whitelisted operators (ADR-006)
  - effects: [Effect]                   # optional state changes when chosen

Effect
  - op: Enum                            # "set" | "inc" | "dec"
  - var: String                         # a declared variable
  - value: any                          # for "set"; numeric for inc/dec
  - once: Boolean                       # optional; applies only the first visit
```

The schema is defined once in Pydantic v2 and exported to `schema/storybook.schema.json`.
It encodes: unique node ids, unique choice ids, unique ending ids, `min`/`max` on integer
variables, optional `once` on effects, and `schema_version`. The loader pins to
`SCHEMA_VERSION = "2.0"` and accepts exactly that version; any other `schema_version` is
rejected outright (see [ADR-001](./adr/adr-001-story-format-json-storybook.md)). A
read-time upcaster chain is not built; migration, if ever needed, is a future decision.

### Operational entities (Postgres)

```text
family            - id, name, created_at
user              - id, family_id, role ("guardian" | "child"), authn_subject
child_profile     - id, family_id, display_name, age_band,
                    reading_level_cap, allowed_content_flags, tts_enabled, avatar
storybook         - id, family_id, current_published_version, status, created_by
storybook_version - storybook_id, version, blob (inline JSONB; blob_ref deferred),
                    validation_report,
                    moderation_report, approved_by, published_at, model, prompt_version
concept           - id, family_id, brief (JSON), created_by
generation_job    - id, concept_id, model, provider, prompt_version,
                    raw_output_ref, validation_report, status, cost, created_at
reading_state     - child_profile_id, storybook_id, version, current_node,
                    var_state (JSON), path (JSON), save_slots (JSON),
                    state_revision (Integer), updated_by_device_id, last_synced_at
completion        - child_profile_id, storybook_id, version, ending_id, found_at
review_item       - storybook_version ref, state, flags (JSON), assigned_to
```

### Relationships

- `family` → `user`, `child_profile`, `storybook`, `concept`: one-to-many (family
  ownership is checked on every resource).
- `storybook` → `storybook_version`: one-to-many; the blob is stored inline in Postgres
  JSONB (`blob`) at launch. Moving it to MinIO behind a `blob_ref` is a deferred future
  path (ADR-009).
- `child_profile` + `storybook` → `reading_state`: per-child, per-story progress.
- `child_profile` + `storybook` → `completion`: one row per ending found.

### Generation and publish lifecycles

Generation and publishing are two separate state machines, not one pipeline. There is no
`generating`, `auto_check`, or `approved` storybook state.

```text
GenerationJob:  queued → running ─┬─► passed        (L1/L2 + moderation gates pass)
                                  ├─► needs_review  (safety flag; a human must clear it)
                                  └─► failed        (hard validation failure)

Storybook:      draft → in_review ─┬─► published → archived
                  ▲                └─► needs_revision → (repair / regenerate) ──┐
                  └────────────────────────── (re-review on edit) ◄────────────┘
```

A story is visible to a child profile only in `published`. The `in_review → published`
transition is a single approve-and-publish action that requires the global **admin** role
(`is_admin`) and is applied cross-family (`authorize_family` is not called on approval). A
draft version becomes reviewable only after its GenerationJob reaches `passed`; a
`needs_review` job routes to a person and a `failed` job routes to repair or regeneration.
See [ADR-005](./adr/adr-005-mandatory-human-approval.md).

### Multi-device sync rules

The server is canonical; IndexedDB is a cache. Concurrency is revision-based, not
last-write-wins.

- Every `reading_state` carries a `state_revision`. A `PUT` includes the
  `state_revision` the client started from; the server applies and increments only if it
  matches, otherwise returns 409 with the current row.
- On 409, the client offers "Continue from this device" (overwrite at the new base
  revision) or "Use newer progress" (adopt server state). Full merge is unnecessary at
  family volume.
- Offline writes queue locally; each carries its base `state_revision` and a
  client-generated `event_id`. On reconnect the client replays in order; the server
  ignores any `event_id` already applied, so replays are idempotent.
- A separate story-version guard protects against saving progress against a different
  published version. If a new version publishes mid-read, the in-progress read freezes on
  its original version (see Runtime Semantics: version pinning).

## Story Runtime Semantics v1

Tier-2 stories behave like tiny programs, so the player and the validator share one
execution model or they will disagree on the one loop nobody tested. These rules are
binding on both.

- **Transition order** (canonical, per choice): evaluate the choice `condition` against
  current state; if visible and chosen, apply the choice `effects`; enter the target
  node; apply the target's `on_enter` effects. Saves and validation assume this exact
  order.
- **Effect application on re-entry**: `on_enter` effects run on every visit by default.
  An effect marked `once: true` applies only the first time its node is entered (tracked
  in `var_state` via an implicit visit set). Use `once` for "you find the lantern."
- **Variable bounds**: `inc`/`dec` are bounded by `min`/`max`. A story where a reachable
  transition would push a variable past its bound is schema-invalid and fails validation;
  rejection is preferred over silent clamping. The runtime clamps only as a defensive
  fallback, treated as a bug to fix in the story.
- **Choice visibility**: a choice whose `condition` is false is hidden, not
  shown-and-disabled. Younger readers should not see locked options they cannot explain.
- **Saves are snapshots**: a save stores `current_node`, `var_state`, `path`, the visit
  set, `save_slots`, the story `version`, and `state_revision`. v1 uses snapshots, not an
  event log.
- **No backtracking in v1**: the reader moves forward only. A "back" button would reopen
  state semantics (undoing effects); deferred until and unless an event-log model is
  added.
- **Endings are identified by `ending.id`**: stable across edits, so the "endings found"
  tracker survives prose changes.
- **Version pinning for in-progress reads**: a reader stays on the `version` they
  started; publishing a new version never mutates an active read.
- **Choice ids are unique within a story**: for audit, debugging, and analytics.

## Story DSL: condition format (ADR-006)

Conditions use the JSONLogic object shape, restricted to a whitelisted operator set,
evaluated by a small in-house interpreter (Python on the backend, TypeScript in the
client). No string parsing; the same object evaluates identically on both sides.

```json
// "you have the lantern"
{ "==": [ { "var": "has_lantern" }, true ] }

// "courage is at least 3 and you do not have the curse"
{ "and": [
  { ">=": [ { "var": "courage" }, 3 ] },
  { "!": { "var": "has_curse" } }
] }
```

Whitelisted operators (everything else is rejected by the validator):

```text
var                                  # read a declared variable
==  !=  <  <=  >  >=                  # comparison
and  or  !                           # boolean (! is "not")
```

Excluded by policy: arithmetic (`+ - * / %`), `in`, string operators (`cat`, `substr`),
array reductions, and `if`/ternary. Each evaluator must be total: any schema-valid
condition returns a boolean without raising. Because every variable carries an `initial`
value, `var` always resolves against populated state. A pinned conformance fixture set
runs each rule through both evaluators and asserts equal results, keeping the validator
and the player in lockstep.

## Authoring Pipeline (staged generation)

- **Stage A: Structure.** Input: concept brief, schema rules, the drafting guide.
  Output: a skeleton (node ids, a one-line beat per node, choice edges, variable
  declarations, ending placement) as JSON, no prose. Validate the skeleton's graph before
  spending tokens on prose.
- **Stage B: Prose.** Input: the approved skeleton. Output: full Storybook JSON with each
  `body` written to the target reading level, age-appropriate, second person. Validate
  again (schema, graph, reading level, length).
- **Stage C: Repair.** Input: the full Storybook plus the validator report. The prompt
  names only the failing node ids and the specific rule violations and instructs the model
  to change nothing else. Cap repairs at 3 attempts. A no-progress detector aborts early if
  the report or output hash is unchanged between attempts. On exhaustion or no progress,
  route to a full regeneration or human review. Never auto-publish.

Between every stage the validator runs deterministically. The model never sees a green
light it did not earn.

### Concept brief (intake fields)

```text
title?, premise, protagonist (name/age/role), point_of_view (default 2nd person),
age_band, reading_level_target, tier, tone, themes_allowed[], content_nogo[],
target_node_count, ending_count, structure_pattern
  (time_cave | gauntlet | branch_and_bottleneck | quest | loop_and_grow),
desired_variables[]?, special_constraints[]?
```

### Validation gate (deterministic, no LLM)

Two layers. Layer 1 (graph) applies to every story. Layer 2 (state-space) applies to
Tier-2 stories, because for stateful stories "the node has a choice" is not the same as
"the reader can actually take one."

**Layer 1: graph (all stories)**

1. **Schema**: conforms to the Storybook JSON Schema.
2. **Reference integrity**: `start_node` exists; every `choice.target` is an existing
   node id; node ids unique; choice ids unique; each `ending` has a unique `id`.
3. **Reachability**: BFS from `start_node` reaches every node. Orphans are errors.
4. **Termination (graph)**: every non-ending node has at least one choice; every node can
   reach an ending; endings have zero choices and an `ending` block.
5. **No trap loops (graph)**: every strongly connected component has at least one exit
   edge.
6. **Condition and effect consistency**: conditions use only whitelisted operators; every
   referenced variable is declared; comparisons agree in type; no reachable transition can
   push a variable past `min`/`max`.
7. **Length budget**: node count within the tier's range; branch depth within bounds;
   `ending_count` equals the number of distinct ending nodes.

**Layer 2: state-space (Tier-2 only)**

A configuration is `(node_id, var_state)`. Because state is booleans and small bounded
integers, the space stays tractable when variables are few.

8. **Configuration walk**: start at `(start_node, initial var_state)`; compute visible
   choices and apply the canonical transition to produce next configurations; explore the
   closure.
9. **Stateful dead-end**: any reachable non-ending configuration with zero visible choices
   fails (the silver-door case).
10. **Stateful termination and loop escape**: every reachable configuration must have a
    path to an ending; every reachable cycle must have an exit toward an ending.
11. **Conditional usefulness**: a conditional choice no reachable configuration can expose
    is flagged (dead branch).
12. **Configuration cap**: if the reachable set exceeds a ceiling (default 100,000), fail
    with "state space too large."

**Reading level (advisory, all stories)**

13. **Reading level**: Flesch-Kincaid grade (textstat) vs `target ± tolerance`. Advisory:
    it warns, never hard-fails, because scores are noisy at passage length and a parent
    makes the final call.

**Safety**

14. **Safety**: moderation over all `body` and `label` text against the age-band policy;
    any hit flags the nodes and forces human review.

Layers 1 and 2 are pass/fail. Reading level warns only. A safety hit always routes to a
person.

## API Specification

Versioned under `/api/v1`. OIDC via Supabase; child sessions are restricted to reader
and library endpoints. The token subject maps to a set of allowed profiles; `profile_id`
is never trusted on its own. Inputs are validated against the published story
(`ending_id` must belong to the cited version; `current_node` must exist in it).

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | /api/v1/library?profile_id={id} | List published stories the profile may see | Yes |
| GET | /api/v1/storybooks/{id}/versions/{v} | Immutable Storybook JSON (ETag, long cache) | Yes |
| GET | /api/v1/reading-state/{profile_id}/{storybook_id} | Read progress | Yes |
| PUT | /api/v1/reading-state/{profile_id}/{storybook_id} | Save progress (revision-guarded) | Yes |
| POST | /api/v1/completions | Record an ending found | Yes |
| POST | /api/v1/concepts | Create a concept brief | Guardian |
| POST | /api/v1/concepts/{id}/generate | Enqueue staged generation | Guardian |
| GET | /api/v1/generation-jobs/{id} | Job status and report | Guardian |
| POST | /api/v1/storybooks/{id}/versions/{v}/validate | Re-run the gate | Guardian |
| PATCH | /api/v1/storybooks/{id}/versions/{v}/nodes/{node_id} | Edit a passage (Phase 4b) | Guardian |
| POST | /api/v1/storybooks/{id}/versions/{v}/submit-review | Move to review | Guardian |
| POST | /api/v1/storybooks/{id}/approve | Approve and publish in one step (→ published) | Admin |

### Request/Response Format (reading-state PUT)

```json
{
  "version": 1,
  "current_node": "n_path",
  "var_state": { "has_lantern": true },
  "path": ["n_start", "n_cellar", "n_path"],
  "save_slots": {},
  "state_revision": 7,
  "device_id": "ipad-briella",
  "event_id": "evt_01H..."
}
```

Story blobs are served backend-mediated from Postgres at launch. Under the deferred
object-storage path they would be served via backend-mediated or signed access from a
private bucket, never a broadly public URL.

## Security

### Authentication

Supabase OIDC (provider-agnostic `oidc_*` config, guardian identities verified via
`jwt.PyJWKClient`); roles `guardian` and `child`, with a guardian-identity vs
child-session split. Child tokens are scoped to reader and library endpoints. See
[ADR-009](./adr/adr-009-supabase-platform.md). Homelab/family-tier deployment remains per
[ADR-004](./adr/adr-004-homelab-first-deployment.md).

### Authorization

Enforced server-side on every endpoint. The token subject maps to an allowed-profile set;
a guardian may act on any profile in their family, a child only on its own assigned
profile. `profile_id` is never trusted alone. The `in_review -> published` transition is a
single approve-and-publish action reserved for the global admin role (`Role.ADMIN` /
`is_admin`), applied cross-family (`authorize_family` is not called on it); no guardian,
including one acting on their own family's story, may perform it. See
[ADR-005](./adr/adr-005-mandatory-human-approval.md) (amended 2026-06-30).

| Action | Guardian | Child (own profile) | Enforcement |
|--------|----------|---------------------|-------------|
| Read own library / story / state | Any family profile | Own profile only | Token subject to allowed-profile set; 403 otherwise |
| Write own reading state | Any family profile | Own profile only | Same, plus `state_revision` and version guards |
| Record a completion | Any family profile | Own profile only | `ending_id` must belong to the published version |
| Generate / submit concept for review | Yes | No (403) | Guardian role required; scoped to own family |
| Approve and publish (single `in_review -> published` transition) | No (403) | No (403) | Global admin role required (`Role.ADMIN` / `is_admin`), cross-family; there is no guardian path |
| Access another family's data | No (403) | No (403) | Family ownership checked on every resource |

**IDOR negative tests** (each expects 403): child A requesting child B's library or state;
a child mutating `profile_id` in a reading-state `PUT`; a child calling approve or publish;
a guardian calling approve or publish, including on their own family's story; a guardian
from another family accessing a story.

### Data Protection

- **At Rest**: encrypt Postgres (which holds the story blobs inline at launch) and, once
  adopted, the deferred object storage.
- **In Transit**: TLS via Pangolin.
- **Content is data, never code**: the only state logic is the in-house whitelisted
  evaluator (ADR-006). No `eval`, no dynamic execution, no third-party logic library in
  the content path.
- **Story blob access**: backend-mediated only; blobs live inline in Postgres at launch.
  A deferred move to object storage would use a private bucket with backend-mediated or
  signed access only.

### Privacy controls (family-only)

- **No real child PII in prompts**: the concept brief passes an age band and a fictional
  reader profile, never a real name, birthdate, or sensitive trait.
- **Raw LLM outputs and prompts are admin-only and short-lived**: store the prompt
  template version and a hash rather than raw prompt text where it could carry
  child-specific detail; retain raw generations only as long as needed for debugging, then
  purge. The retention purge is a scheduled pg_cron job per
  [ADR-007](./adr/adr-007-raw-output-retention.md) and
  [ADR-009](./adr/adr-009-supabase-platform.md) (Phase 5, not yet built). Moderation
  reports persist with the story version for audit.
- **Deletion-readiness**: keep child-linked data in known places (Postgres rows and inline
  blobs, plus deferred-future object-storage blobs, raw generations); do not scatter it
  through logs and Sentry. A full deletion
  subsystem is a later deliverable; the requirement now is that the data model does not make
  deletion impossible.
- **Prompt-injection defense**: concept-brief text is untrusted; the generation system
  prompt and safety constraints are fixed and cannot be altered by brief content;
  moderation runs independently of the generating model.
- **If shared beyond family**: this design is built for private use. Before any non-family
  use, revisit with counsel (COPPA and state equivalents, age assurance, verifiable
  parental consent, retention/deletion policy, vendor terms, incident response, a published
  privacy notice). The COPPA Rule and the ICO Age Appropriate Design Code are design
  references, not legal advice.

## Error Handling

### Strategy

Fail fast on validation; degrade gracefully on the reader (offline). Generation failures
are caught, logged with the raw output stored for inspection, and retried under the repair
cap.

### Error Codes

| Code | Meaning | User Action |
|------|---------|-------------|
| 401 | Unauthenticated | Sign in via Supabase |
| 403 | Profile or role not permitted | None (blocked by design) |
| 404 | Story or version not found | Refresh the library |
| 409 | Reading-state revision or version mismatch | Choose "this device" or "newer progress" |
| 422 | Input not valid against the published story | Correct `current_node` / `ending_id` |

### Logging

- **Format**: structured JSON with correlation ids (see project logging conventions).
- **Levels**: DEBUG, INFO, WARNING, ERROR.
- **Sensitive**: never log a child's reading content beyond an id; Sentry for exceptions
  on client and server.

## Performance Requirements

| Metric | Target | Measurement |
|--------|--------|-------------|
| Node transition | < 50 ms | Client-side from cache |
| First meaningful paint | < 2 s | Home wifi, real device |
| Library list | < 300 ms | API response |
| Validation | < 2 s | 200-node story |
| Generation | ~3 to 5 min | 30-to-60-node Tier-2 story, async |
| Story blob size | < 500 KB | Per Storybook, for offline caching |

## Testing Strategy

### Coverage Target

- Minimum: 80% line, 70% branch (per project standards); critical paths and patch
  coverage 90%.

### Test Types

- **Unit**: each in-house condition evaluator (property-based: Hypothesis and fast-check
  for totality); each validator rule; the schema round-trip (Pydantic to JSON Schema); each
  upcaster against its golden fixture.
- **Cross-implementation conformance**: a pinned `(condition, var_state, expected boolean)`
  fixture set run through both evaluators, asserting identical results.
- **Runtime semantics**: fixtures asserting transition order, `once` on re-entry, bound
  rejection, hidden-vs-shown choices, and version pinning, played identically by the test
  harness and the browser player.
- **State-space validator**: a Tier-2 corpus including the silver-door dead end, a
  state-reachable trap cycle, an unsatisfiable conditional, a bound-overflow transition, and
  a configuration-cap blowup.
- **Golden corpus**: hand-authored valid stories and a curated known-bad set (dangling
  target, orphan node, unreachable ending, trap loop, unsatisfiable condition, reading-level
  miss, unsafe content). Accept all valid, reject all invalid.
- **Authorization / IDOR**: the negative tests above; an unapproved or off-band story never
  appears in a child's library.
- **Integration**: the generation pipeline with a mocked provider returning canned and
  deliberately malformed outputs, proving the repair loop, the no-progress abort, and the
  gate.
- **End-to-end (Playwright)**: a full playthrough including offline mode, save/resume,
  multi-device 409 reconciliation, read-aloud, and the ending tracker.
- **Safety evaluation**: adversarial concept briefs verifying moderation flags and the
  human gate cannot be bypassed.
- **CI/CD and security baseline**: Ruff, BasedPyright, Bandit, detect-secrets, OSV-Scanner,
  CodeQL, SonarCloud, Trivy, CycloneDX SBOM, Cosign; ESLint, Prettier, Vitest, Playwright.

## Related Documents

- [Project Vision](./project-vision.md)
- [Architecture Decisions](./adr/README.md)
- [Development Roadmap](./roadmap.md)
