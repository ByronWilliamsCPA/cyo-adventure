# Technical Baseline

> **Status**: Phase 0 deliverable (P0-07, P0-13) | **Updated**: 2026-06-20
> **Codename**: Ariadne

This file pins the exact component versions and records the migration convention
the project builds on. It is the source of truth for "what version" questions.
Container images are pinned by tag; `latest` is never used in production.

## Runtime and toolchain

| Component | Pin | Notes |
|-----------|-----|-------|
| Python (target) | 3.14 (ruff `target-version = "py311"` floor) | Supported range `>=3.11`. CI runs 3.14. |
| Node | 22 (`node:22-alpine`) | Frontend build and dev. |
| uv | project-managed | `uv.lock` is the reproducible source of truth. |
| pnpm / npm | npm (template default) | Frontend package manager. |

> Local note: 3.14 is now the primary interpreter everywhere (local, CI, and
> the production runtime image), so developer virtualenvs resolving to 3.14
> match CI instead of drifting from it.

## Backend (resolved from `uv.lock`)

| Package | Version | Role |
|---------|---------|------|
| fastapi | 0.138.0 | API framework |
| pydantic | 2.13.4 | Schema and validation (Storybook schema v1) |
| pydantic-settings | 2.14.2 | Configuration |
| sqlalchemy | 2.0.51 | ORM (async) |
| supabase CLI | 2.109.1 | Migrations (ADR-012) |
| uvicorn | 0.49.0 | ASGI server |
| structlog | 26.1.0 | Structured logging |
| rich | 15.0.0 | Console logging (dev) |

### Planned additions (pin at add time, per phase)

These are committed by the plan but not yet added; pin the resolved version when
`uv add` runs in the phase that needs it.

| Package | Phase | Role | Decision reference |
|---------|-------|------|--------------------|
| networkx | 1 | Graph reachability, cycle, termination (Layer-1 validator) | tech-spec |
| textstat | 2 | Flesch-Kincaid grade (advisory reading-level rule) | tech-spec RL-13 |
| rq | 2 | Background generation queue (chosen over Celery for simplicity at this scale) | ADR-004, confirmed |
| anthropic | 2 | Claude provider behind the `GenerationProvider` interface | ADR-003 |
| hypothesis | 1 | Property-based totality tests for the condition evaluator | tech-spec testing |

**Condition evaluator**: in-house, no third-party logic library (ADR-006). This is
confirmed; the only state logic in the content path is the whitelisted evaluator
(`src/cyo_adventure/storybook/condition.py` for shape; the evaluating interpreter
lands in Phase 1).

## Frontend (`frontend/package.json`)

| Package | Pin | Role |
|---------|-----|------|
| react / react-dom | ^19.0.0 | UI |
| typescript | ~5.7.2 | Types |
| vite | ^6.0.6 | Build and dev server |
| vitest | ^2.1.8 | Unit tests |
| axios | ^1.7.9 | HTTP client |

### Planned frontend additions (Phase 1)

| Package | Role | Decision reference |
|---------|------|--------------------|
| vite-plugin-pwa (Workbox) | Service worker, offline caching | ADR-002 |
| xstate | Player state machine | ADR-002, tech-spec |
| idb | IndexedDB cache wrapper | ADR-002 |
| fast-check | Property-based evaluator conformance | tech-spec testing |
| @playwright/test | Offline / save-resume / 409 E2E | tech-spec testing |

## Container images

| Image | Tag | Status |
|-------|-----|--------|
| python | `3.14-slim-bookworm` (builder) / `dhi-python:3.14-debian13` (runtime) | Pinned (Dockerfile) |
| node | `22-alpine` | Pinned (frontend Dockerfile) |
| nginx | `alpine` | Frontend production serve; pin to a digest/tag before release |
| postgres | `16-alpine` | Pinned (compose) |
| redis | `7-alpine` | Pinned (compose, currently commented; enable for the RQ queue) |
| cyo_adventure (app) | `${VERSION:-latest}` | **Finding**: `latest` fallback in `docker-compose.yml`. Set `VERSION` explicitly in every environment; flagged in `docs/template_feedback.md`. |
| cyo_adventure-frontend | `${VERSION:-latest}` | Same finding as above. |

## Supabase migration convention (ADR-012)

- **Location**: `supabase/migrations/`, plain SQL, applied by the pinned
  Supabase CLI.
- **Naming**: `<YYYYMMDDHHMMSS>_<short_slug>.sql` (CLI-generated via
  `supabase migration new <slug>`); never rename or edit a migration once it
  is on `main`.
- **Ordering**: lexicographic by timestamp; the chain is linear on `main`.
- **Forward-only**: no downgrade scripts. Recovery is roll-forward; every
  migration is rehearsed on staging (merge to `main`) before production
  (approved dispatch). Destructive data migrations must document a manual
  recovery note in a leading SQL comment.
- **Drift guard**: `tests/integration/test_schema_parity.py` fails CI when
  the migrated schema and `Base.metadata` disagree.
- **CI migration check**: `supabase-ci.yml` applies the full chain to a fresh
  local stack on every PR touching `supabase/`.

## How to refresh this file

After any `uv add` / `uv sync --upgrade` or frontend dependency bump, re-read the
resolved versions (`uv.lock`, `frontend/package.json`) and update the tables here.
Regenerate the JSON Schema if the Pydantic models changed:

```bash
uv run python -m cyo_adventure.storybook.schema_export
```
