---
title: "Architecture"
schema_type: common
status: published
owner: core-maintainer
purpose: "Architecture documentation entry point for the development guide."
tags:
  - development
  - architecture
---

The full system architecture documentation lives under `docs/architecture/`. This page
provides a brief orientation and links to each section.

## Architecture Documentation

| Section | Contents |
| ------- | -------- |
| [Architecture Overview](../architecture/README.md) | Index of all diagrams and ADRs |
| [System Overview](../architecture/system-overview.md) | C4 context and container diagrams; actors, external systems, publish state machine |
| [Generation Pipeline](../architecture/generation-pipeline.md) | Staged LLM generation (Structure/Prose/Repair), provider fallback cascade, PII guard |
| [Validation and Player](../architecture/validation-and-player.md) | Validator gate layers, story engine (Runtime Semantics v1), offline sync |
| [Data Model](../architecture/data-model.md) | ER diagram, 9 ORM tables, foreign key relationships |
| [Deployment](../architecture/deployment.md) | Homelab Docker stack (ADR-004), Pangolin, Authentik, MinIO (Phase 5) |

## Project Structure

```text
src/cyo_adventure/
├── api/                    # FastAPI routers (all under /api/v1)
│   ├── deps.py             # Principal, auth seam, RequestContext
│   ├── generation.py       # Guardian-only: concepts, jobs, validate
│   ├── health.py           # Liveness / readiness / startup probes
│   ├── library.py          # Story library (age-band filtered)
│   ├── reading.py          # Reading state + completions (OCC)
│   └── schemas.py          # Pydantic request / response models
├── core/
│   ├── config.py           # Pydantic Settings (env vars + .env)
│   ├── database.py         # Async SQLAlchemy engine, Base, get_session()
│   └── exceptions.py       # Centralized exception hierarchy
├── db/
│   └── models.py           # 9 ORM tables (Family, User, ChildProfile,
│                           # Storybook, StorybookVersion, ReadingState,
│                           # Completion, Concept, GenerationJob)
├── generation/
│   ├── concept.py          # ConceptBrief Pydantic model
│   ├── orchestrator.py     # generate_story(): Stage A -> B -> C pipeline
│   ├── pii.py              # PII guard (assert_prompt_pii_safe)
│   ├── prompts.py          # Cacheable prompt block builders
│   ├── provider.py         # GenerationProvider protocol
│   ├── providers/
│   │   ├── fallback.py     # FallbackProvider cascade (Layer 2)
│   │   ├── ollama.py       # Ollama adapter (Layer 1, local fallback)
│   │   └── openrouter.py   # OpenRouter adapter (Layer 1, primary)
│   ├── queue.py            # enqueue_generation() (RQ)
│   └── worker.py           # RQ worker entry point
├── middleware/
│   ├── correlation.py      # CorrelationMiddleware (must be first)
│   └── security.py         # OWASP headers, HSTS, SSRF protection
├── player/
│   ├── engine.py           # StoryEngine: Runtime Semantics v1 (pure)
│   └── state.py            # ReadingState dataclass
├── storybook/
│   ├── condition.py        # Condition DSL validator
│   ├── evaluator.py        # evaluate(): whitelisted-op condition evaluator
│   ├── models.py           # Storybook, Node, Choice, Effect (Pydantic v2)
│   └── schema_export.py    # Export JSON schema for validator Layer 1
├── utils/
│   ├── financial.py        # Template scaffolding (Decimal helpers; unused)
│   └── logging.py          # Structlog structured logging with correlation
└── validator/
    ├── gate.py             # run_gate(): L1 -> L2 -> RL -> SAFE, GateResult
    ├── layer1.py           # L1-1..L1-7 graph structure rules (networkx)
    ├── layer2.py           # L2-9..L2-12 state-space walk (Tier-2 only)
    ├── reading_level.py    # RL-13 advisory check (textstat, WARNING)
    ├── report.py           # ValidationReport, ValidationFinding, Severity
    ├── safety.py           # SAFE-14 stub (Phase 2, always empty)
    └── walk.py             # BFS/DFS state-space walker

frontend/
└── src/
    ├── api/                # Typed API call helpers
    ├── client/             # Generated OpenAPI client (BUILD OUTPUT - do not edit)
    ├── components/         # Shared UI components
    ├── hooks/              # React hooks
    ├── offline/
    │   ├── db.ts           # IndexedDB: local cache + write queue
    │   └── sync.ts         # saveProgress(), replayQueue(), OfflineError
    ├── player/
    │   ├── engine.ts       # TypeScript mirror of engine.py (Runtime Semantics v1)
    │   ├── evaluator.ts    # TypeScript mirror of evaluator.py
    │   └── machine.ts      # XState machine wrapping the TS engine
    └── reader/             # Reader UI components
```

## Design Principles

**Type safety:** BasedPyright strict mode on the backend; `tsc --strict` on the frontend.
All inbound data crosses Pydantic v2 models before reaching business logic.

**Structured logging:** Structlog emits JSON logs with correlation IDs injected by
`CorrelationMiddleware` into every log line for the request lifecycle.

**Configuration management:** Pydantic Settings (`core/config.py`) loads from
environment variables and `.env` files. The dev database URL raises `ConfigurationError`
if detected in a non-local environment.

**Exception hierarchy:** All domain errors are raised from `core/exceptions.py`.
FastAPI exception handlers map them to HTTP status codes. Route handlers never raise
built-in exceptions directly.

## Architecture Decision Records

See the [ADR index](../planning/adr/README.md) for all six accepted decisions. The
[Architecture Overview](../architecture/README.md#architecture-decision-records) table
links each ADR to the relevant system area.
