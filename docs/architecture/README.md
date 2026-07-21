---
title: "Architecture Overview"
schema_type: common
status: published
owner: core-maintainer
purpose: "Index of architecture documentation, diagrams, and ADRs for CYO Adventure."
tags:
  - architecture
  - overview
---

CYO Adventure is a choose-your-own-adventure reading app for kids. A React 19 PWA
lets children read branching stories offline; a FastAPI backend serves the library,
manages reading progress, and runs an LLM-powered generation pipeline behind a
deterministic validation gate and mandatory admin approval (ADR-005).

## Architecture Pages

| Page | Description |
| ---- | ----------- |
| [User Journeys](user-journeys.md) | UX-flow set: end-to-end, per-surface (kid, guardian), and a developer test-coverage view |
| [System Overview](system-overview.md) | C4 context and container diagrams; publish state machine |
| [Generation Pipeline](generation-pipeline.md) | Staged LLM generation (Structure/Prose/Repair), provider fallback |
| [Validation and Player](validation-and-player.md) | Validator gate, story engine, offline sync |
| [Data Model](data-model.md) | 22 ORM tables, ER diagram, relationships |
| [Story Skeletons](story-skeletons.md) | Preset skeleton structure diagrams and metadata data dictionary |
| [Deployment](deployment.md) | Homelab Docker stack, Pangolin, Supabase auth, MinIO (deferred Phase 5) |

## Diagram Index

All diagrams are PlantUML source + rendered SVG pairs under `docs/architecture/diagrams/`.
The full catalog, with per-diagram source-file traceability, is in
[diagrams/INDEX.md](diagrams/INDEX.md). Authoring and styling conventions (the colour
palette, the `@startuml`-name rule, status stereotypes, traceability notes) are in
[diagrams/STYLE_GUIDE.md](diagrams/STYLE_GUIDE.md); shared skinparams and colour constants
live in [diagrams/style.puml](diagrams/style.puml).

To regenerate SVGs after editing a PUML file, use the generator (it resolves and
SHA-256-verifies the pinned PlantUML **1.2024.7** jar for you, so there is no ephemeral
`/tmp/plantuml.jar` to manage):

```bash
python tools/generate_diagram_svgs.py          # re-render diagrams with a stale SVG
python tools/generate_diagram_svgs.py --all     # force a full re-render
python tools/generate_diagram_svgs.py --check   # CI gate: non-zero if any SVG is stale
```

The auto-generated story-skeleton diagrams under `diagrams/skeletons/` are owned by
`scripts/render_skeleton_diagrams.py`, not this tool.

## System at a Glance

```text
Family devices (browsers, tablets)
  |  HTTPS (Pangolin zero-trust)
  v
PWA (React 19, TypeScript)
  - Reader: XState + TS engine + TS evaluator
  - Offline: IndexedDB cache + write queue (event_id idempotency)
  - API client: generated from OpenAPI schema (not hand-written)
  |  REST /api/v1 + Bearer token (OIDC via Supabase Auth)
  v
FastAPI backend (Python 3.12)
  - api/: 28 routers -- health, library, reading, reading_history, generation,
                 profiles, families, ratings, assignments, approval (global admin),
                 node_edit, covers, moderation_thresholds, moderation_dashboard,
                 audit, rescreen, provider_allowlist, me, story_requests,
                 child_sessions, device_grants (ADR-014), onboarding, flags,
                 notifications, admin_users, admin_profiles, family_connections,
                 recommendations (#270 M4b-d + #277)
  - api/deps.py: Principal (role/family/profile) auth seam; Role.DEVICE
                 routing branch for the device grant (ADR-014)
  - storybook/: Pydantic models, condition DSL, evaluator
  - player/: StoryEngine (Runtime Semantics v1, pure)
  - validator/: gate (L1+L2+RL+SAFE), walk, report
  - generation/: orchestrator (Stage A->B->C fresh_generation, or
                 skeleton_fill via fill_skeleton), prompts, PII guard
                 (guarded.PiiGuardedProvider wrapper), skeleton
                 catalog + cell-aware matching (WS-C PR2), series
                 continuation chaining (WS-G),
                 providers (default 3-leg cascade: OpenRouter haiku
                 primary, OpenRouter sonnet fallback, then Ollama local;
                 Anthropic and Modal are additional per-job-selectable
                 legs behind the admin ProviderModelAllowlist, WS-C PR1),
                 FallbackProvider cascade, queue, worker
  - moderation/: classifiers, fidelity review, thresholds (per-band/
                 category overrides + admin noise floor), repair
  - events/: append-only pipeline_event writer (WS-D)
  - publishing/: approve -> publish state machine
  - middleware/: CorrelationMiddleware (first), SecurityMiddleware (OWASP)
  |
  +-- PostgreSQL 16 (async SQLAlchemy 2, 22 tables, Supabase CLI SQL migrations)
  +-- Redis 7 (RQ job queue)
  |
  +-- [worker container] RQ worker
        -> OpenRouter haiku (leg 1, primary)
        -> OpenRouter sonnet (leg 2, fallback)
        -> Ollama (leg 3, local fallback)
        -> Anthropic / Modal (admin-selectable, per job)
        -> [Phase 5] MinIO (blob_ref object storage)
```

## Key Design Decisions

| Decision | Rationale |
| -------- | --------- |
| Mandatory admin approval (ADR-005) | No story reaches a child without a human (global admin) in the loop |
| JSON Storybook format (ADR-001) | Deterministic, validatable, no runtime parsing ambiguity |
| PWA offline-first (ADR-002) | Children can read without network connectivity |
| Staged LLM generation with repair (ADR-003) | Improves schema conformance; bounded, not unbounded retries |
| In-house condition evaluator (ADR-006) | No third-party logic library; whitelisted ops only |
| Homelab-first deployment (ADR-004) | Family privacy; zero cloud dependency for core features |

## Architecture Decision Records

| ADR | Title | Status |
| --- | ----- | ------ |
| [ADR-001](../planning/adr/adr-001-story-format-json-storybook.md) | Story format: JSON Storybook | Accepted |
| [ADR-002](../planning/adr/adr-002-client-pwa.md) | Client: Progressive Web App | Accepted |
| [ADR-003](../planning/adr/adr-003-frontier-llm-generation.md) | Frontier LLM story generation | Accepted |
| [ADR-004](../planning/adr/adr-004-homelab-first-deployment.md) | Homelab-first deployment | Accepted |
| [ADR-005](../planning/adr/adr-005-mandatory-human-approval.md) | Mandatory human approval gate | Accepted |
| [ADR-006](../planning/adr/adr-006-conditions-inhouse-evaluator.md) | Conditions: in-house evaluator | Accepted |
