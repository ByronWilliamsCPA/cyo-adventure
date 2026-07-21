---
title: "Diagram Index"
schema_type: common
status: published
owner: core-maintainer
purpose: "Canonical catalog of the hand-authored CYO Adventure architecture diagrams with source-file traceability."
tags:
  - architecture
  - reference
  - tooling
---

Canonical catalog of the hand-authored top-level diagrams under
`docs/architecture/diagrams/`. Each entry is a PlantUML source (`.puml`) plus its
committed, rendered `.svg`. Styling conventions and the regeneration workflow are in
[STYLE_GUIDE.md](STYLE_GUIDE.md); shared skinparams and the colour palette are in
[style.puml](style.puml).

The ~60 auto-generated story-skeleton diagrams under `skeletons/` are **not** listed
here: they are produced from skeleton JSON by `scripts/render_skeleton_diagrams.py` and
cataloged in [../story-skeletons.md](../story-skeletons.md).

## C4 (structure)

| Diagram | Files | Primary sources | Description |
| ------- | ----- | --------------- | ----------- |
| C4 Context (L1) | [c4-context.puml](c4-context.puml) / [.svg](c4-context.svg) | `api/deps.py`, `api/device_grants.py`, `core/device_grant.py`, `db/models.py` | Actors (child, guardian, admin) and external systems |
| C4 Container (L2) | [c4-container.puml](c4-container.puml) / [.svg](c4-container.svg) | `app.py`, `api/`, `generation/worker.py`, `core/database.py`, `frontend/src/client/`, `frontend/src/offline/sync.ts` | Runtime containers and data stores |

## Components

| Diagram | Files | Primary sources | Description |
| ------- | ----- | --------------- | ----------- |
| Generation Pipeline | [component-generation.puml](component-generation.puml) / [.svg](component-generation.svg) | `generation/orchestrator.py`, `prompts.py`, `pii.py`, `guarded.py`, `provider.py`, `allowlist.py`, `skeleton_catalog.py` | Orchestrator, prompts, providers, PII guard |
| Validator Gate | [component-validator.puml](component-validator.puml) / [.svg](component-validator.svg) | `validator/gate.py`, `layer1.py`, `policy.py`, `band_profile.py`, `layer2.py`, `reading_level.py`, `safety.py` | L1 / Policy / L2 / RL / SAFE layers |
| Player Engine | [component-player.puml](component-player.puml) / [.svg](component-player.svg) | `player/engine.py`, `state.py`, `replay.py`, `storybook/models.py`, `evaluator.py`, `condition.py` | StoryEngine, evaluator, condition DSL |
| API and Persistence | [component-api-persistence.puml](component-api-persistence.puml) / [.svg](component-api-persistence.svg) | `app.py`, `api/health.py`, `library.py`, `reading.py`, `generation.py`, `profiles.py`, `families.py` | Routers, auth seam, ORM |
| Moderation Pipeline | [component-moderation.puml](component-moderation.puml) / [.svg](component-moderation.svg) | `moderation/pipeline.py`, `classifiers.py`, `stages.py`, `repair.py`, `report.py`, `review_provider.py`, `thresholds.py` | Stage 0-4 review, auto-repair, thresholds |
| Publishing | [component-publishing.puml](component-publishing.puml) / [.svg](component-publishing.svg) | `publishing/state_machine.py`, `service.py`, `api/approval.py`, `review_surface.py`, `events/writer.py` | Approval state machine, admin-only approve (ADR-005) |
| Pipeline Event Log | [component-events.puml](component-events.puml) / [.svg](component-events.svg) | `events/models.py`, `writer.py`, `db/models.py`, plus every workflow writer (`generation/worker.py`, `moderation/pipeline.py`, `publishing/service.py`, `story_requests/service.py`) | Append-only PipelineEvent writers |

## Sequences

| Diagram | Files | Primary sources | Description |
| ------- | ----- | --------------- | ----------- |
| Generation Sequence | [seq-generation.puml](seq-generation.puml) / [.svg](seq-generation.svg) | `generation/orchestrator.py`, `provider.py`, `providers/fallback.py`, `core/config.py`, `pii.py`, `guarded.py` | Stage A/B/C with provider fallback |
| Reading-State PUT | [seq-reading-state.puml](seq-reading-state.puml) / [.svg](seq-reading-state.svg) | `api/reading.py`, `api/schemas.py`, `db/models.py` | Optimistic concurrency, 409 reconciliation |
| Offline and Reconnect | [seq-offline.puml](seq-offline.puml) / [.svg](seq-offline.svg) | `frontend/src/offline/sync.ts`, `db.ts`, `reader/ReaderPage.tsx`, `hooks/useReplayOnReconnect.ts` | IndexedDB queue, replay, conflict |
| Device Grant Sequence | [seq-device-grant.puml](seq-device-grant.puml) / [.svg](seq-device-grant.svg) | `core/device_grant.py`, `api/device_grants.py`, `deps.py`, `child_sessions.py`, `frontend/src/auth/deviceGrant.ts`, `DeviceAuthorizedRoute.tsx` | ADR-014: mint / verify / revoke |

## Data

| Diagram | Files | Primary sources | Description |
| ------- | ----- | --------------- | ----------- |
| ER Diagram | [er-diagram.puml](er-diagram.puml) / [.svg](er-diagram.svg) | `db/models.py` | All 22 ORM tables and FK relationships |

## Deployment and routing

| Diagram | Files | Primary sources | Description |
| ------- | ----- | --------------- | ----------- |
| Deployment | [deployment.puml](deployment.puml) / [.svg](deployment.svg) | `core/device_grant.py`, `core/config.py`, `docker-compose*.yml` | Docker containers, Pangolin, Supabase OIDC, device-grant secret |
| Sitemap and Flows | [sitemap-and-flows.puml](sitemap-and-flows.puml) / [.svg](sitemap-and-flows.svg) | `frontend/src/router.tsx`, `routes.ts`, `landing/LandingPage.tsx`, `auth/DeviceAuthorizedRoute.tsx`, `AdultGate.tsx`, `ProtectedRoute.tsx` | Every route and its purpose; two auth-boundary crossings (ADR-014) |

## User journeys

| Diagram | Files | Primary sources | Description |
| ------- | ----- | --------------- | ----------- |
| End-to-End Journey | [journey-end-to-end.puml](journey-end-to-end.puml) / [.svg](journey-end-to-end.svg) | `frontend/src/router.tsx`, `landing/LandingPage.tsx`, `auth/DeviceAuthorizedRoute.tsx`, `AdultGate.tsx`, `library/RequestStory.tsx`, `guardian/RequestsPage.tsx` | Target-state UX across Child/Guardian/Admin/System lanes |
| Kid-Surface Journey | [journey-kid.puml](journey-kid.puml) / [.svg](journey-kid.svg) | `frontend/src/router.tsx`, `auth/DeviceAuthorizedRoute.tsx`, `deviceGrant.ts`, `kid/ProfilePickerPage.tsx`, `library/LibraryPage.tsx`, `reader/Reader.tsx` | Zoomed child-facing flow |
| Guardian + Admin Journey | [journey-guardian.puml](journey-guardian.puml) / [.svg](journey-guardian.svg) | `frontend/src/router.tsx`, `auth/AdultGate.tsx`, `guardian/LoginPage.tsx`, `ConsolePage.tsx`, `admin/AdminConsolePage.tsx`, `IntakePage.tsx`, `RequestsPage.tsx`, `BooksPage.tsx` | Zoomed parent + admin flow (approve is admin-only, ADR-005) |
| Journey Test Coverage | [journey-dev-coverage.puml](journey-dev-coverage.puml) / [.svg](journey-dev-coverage.svg) | `frontend/src/**/*.test.tsx` (Vitest) | Journey recolored by e2e / unit / none coverage |

## Maintenance

- Regenerate SVGs after editing any `.puml` with `python tools/generate_diagram_svgs.py`
  (or `--all` to force, `--check` as a freshness gate). See
  [STYLE_GUIDE.md](STYLE_GUIDE.md#regenerating-svgs).
- The `Primary sources` column is a maintenance aid, not an exhaustive list; each
  `.puml` carries a full `' Source files:` traceability block. A source path that no
  longer exists is drift the diagram audit will flag.
