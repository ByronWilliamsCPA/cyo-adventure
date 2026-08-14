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
| Generation Pipeline | [component-generation.puml](component-generation.puml) / [.svg](component-generation.svg) | `generation/orchestrator.py`, `prompts.py`, `pii.py`, `guarded.py`, `provider.py`, `allowlist.py`, `skeleton_catalog.py`, `binding.py`, `fidelity_gate.py`, `fidelity.py`, `reading_level_loop.py` | Orchestrator, prompts, providers, PII guard, WS-2 theme binding, Stage-1 fidelity gate, Stage D reading-level loop |
| Validator Gate | [component-validator.puml](component-validator.puml) / [.svg](component-validator.svg) | `validator/gate.py`, `layer1.py`, `policy.py`, `band_profile.py`, `layer2.py`, `character.py`, `reading_level.py`, `safety.py`, `choice_grammar.py` | L1 / Policy / L2 / CH / RL / CG / SAFE layers. Note CH (`character.py`, ADR-028) is BLOCKING, not advisory: `run_gate()`'s blocked prefix set is CH/L1/L2/PL. Also notes sentinel_integrity.py, slots.py, theme_leak.py, series.py, paths.py as siblings not called by run_gate() |
| Player Engine | [component-player.puml](component-player.puml) / [.svg](component-player.svg) | `player/engine.py`, `state.py`, `replay.py`, `stops.py`, `storybook/models.py`, `evaluator.py`, `condition.py` | StoryEngine, evaluator, condition DSL, ADR-026 stop composition, ADR-023 personalization modules |
| API and Persistence | [component-api-persistence.puml](component-api-persistence.puml) / [.svg](component-api-persistence.svg) | `app.py`, `api/health.py`, `library.py`, `reading.py`, `generation.py`, `profiles.py`, `families.py`, `consent.py`, `characters.py`, `offline_downloads.py`, `kws_webhook.py`, `kws_redirect.py` | All 37 wired routers (38 `include_router()` calls: health mounts twice), auth seam, ORM |
| Moderation Pipeline | [component-moderation.puml](component-moderation.puml) / [.svg](component-moderation.svg) | `moderation/pipeline.py`, `classifiers.py`, `stages.py`, `repair.py`, `report.py`, `review_provider.py`, `thresholds.py`, `leaf_diversity.py`, `personalizable_slots.py`, `synthesis.py` | Stage 0-4 review, auto-repair, thresholds, WS-1 leaf-diversity guard, findings synthesis |
| Publishing | [component-publishing.puml](component-publishing.puml) / [.svg](component-publishing.svg) | `publishing/state_machine.py`, `service.py`, `catalog_publish.py`, `reason_codes.py`, `api/approval.py`, `review_surface.py`, `events/writer.py` | Approval state machine, admin-only approve (ADR-005), standalone catalog-publish CLI, closed send-back reason vocabulary |
| Pipeline Event Log | [component-events.puml](component-events.puml) / [.svg](component-events.svg) | `events/models.py`, `writer.py`, `db/models.py`, plus every workflow writer (`generation/worker.py`, `moderation/pipeline.py`, `publishing/service.py`, `story_requests/service.py`) | Append-only PipelineEvent writers |

## Sequences

| Diagram | Files | Primary sources | Description |
| ------- | ----- | --------------- | ----------- |
| Generation Sequence | [seq-generation.puml](seq-generation.puml) / [.svg](seq-generation.svg) | `generation/orchestrator.py`, `provider.py`, `providers/fallback.py`, `core/config.py`, `pii.py`, `guarded.py`, `reading_level_loop.py` | Stage A/B/C with provider fallback, then Stage D (reading level). The diagram is otherwise fresh_generation-only; Stage D is the exception, running on both methods |
| Reading-State PUT | [seq-reading-state.puml](seq-reading-state.puml) / [.svg](seq-reading-state.svg) | `api/reading.py`, `api/schemas.py`, `db/models.py` | Optimistic concurrency, 409 reconciliation |
| Offline and Reconnect | [seq-offline.puml](seq-offline.puml) / [.svg](seq-offline.svg) | `frontend/src/offline/sync.ts`, `db.ts`, `reader/ReaderPage.tsx`, `reader/ReaderRoute.tsx`, `hooks/useReplayOnReconnect.ts` | IndexedDB queue, replay, and silent newest-write-wins conflict resolution. There is no conflict dialog on the child path and no `ConflictDialog` component: `offline-conflict-ux.md` section 1's dialog was superseded 2026-07-22 |
| Device Grant Sequence | [seq-device-grant.puml](seq-device-grant.puml) / [.svg](seq-device-grant.svg) | `core/device_grant.py`, `core/child_session.py`, `core/pin.py`, `core/token_audience.py`, `api/device_grants.py`, `deps.py`, `child_sessions.py`, `frontend/src/auth/deviceGrant.ts`, `DeviceAuthorizedRoute.tsx` | ADR-014: mint / verify / revoke |
| KWS Parent Verification | [seq-kws-verification.puml](seq-kws-verification.puml) / [.svg](seq-kws-verification.svg) | `consent/service.py`, `consent/kws_client.py`, `consent/external_payload.py`, `api/kws_webhook.py`, `api/kws_redirect.py`, `core/config.py`, `db/models.py` | ADR-018 D1: three legs, three trust properties. Only the webhook may write consent state; the redirect return is replayable by construction and is display-only |

## Data

| Diagram | Files | Primary sources | Description |
| ------- | ----- | --------------- | ----------- |
| ER Diagram | [er-diagram.puml](er-diagram.puml) / [.svg](er-diagram.svg) | `db/models.py` | All 31 ORM tables and FK relationships |
| ER Diagram (Mermaid) | [er-diagram.mmd](er-diagram.mmd), embedded in [../data-model.md](../data-model.md) | `db/models.py` | Same 31 tables/relationships as `er-diagram.puml`, in Mermaid for inline rendering on GitHub. Hand-maintained companion, not covered by `tools/generate_diagram_svgs.py`; update alongside `er-diagram.puml` when the schema changes. |

## Deployment and routing

| Diagram | Files | Primary sources | Description |
| ------- | ----- | --------------- | ----------- |
| Deployment | [deployment.puml](deployment.puml) / [.svg](deployment.svg) | `core/device_grant.py`, `core/config.py`, `docker-compose*.yml` | Docker containers, Pangolin, Supabase OIDC, device-grant secret |
| Sitemap and Flows | [sitemap-and-flows.puml](sitemap-and-flows.puml) / [.svg](sitemap-and-flows.svg) | `frontend/src/router.tsx`, `routes.ts`, `landing/LandingPage.tsx`, `auth/DeviceAuthorizedRoute.tsx`, `AdultGate.tsx`, `ProtectedRoute.tsx`, `GuardianVerificationPage.tsx`, `legal/PrivacyPolicyPage.tsx`, `legal/SupportPage.tsx` | Every route and its purpose; two auth-boundary crossings (ADR-014); the four `ProtectedRoute` interstitials in the order it checks them; and the public, ungated-by-construction `/privacy` and `/support` pair |

## User journeys

| Diagram | Files | Primary sources | Description |
| ------- | ----- | --------------- | ----------- |
| End-to-End Journey | [journey-end-to-end.puml](journey-end-to-end.puml) / [.svg](journey-end-to-end.svg) | `frontend/src/router.tsx`, `landing/LandingPage.tsx`, `auth/DeviceAuthorizedRoute.tsx`, `AdultGate.tsx`, `library/RequestStory.tsx`, `guardian/RequestsPage.tsx` | Target-state UX across Child/Guardian/Admin/System lanes |
| Kid-Surface Journey | [journey-kid.puml](journey-kid.puml) / [.svg](journey-kid.svg) | `frontend/src/router.tsx`, `auth/DeviceAuthorizedRoute.tsx`, `deviceGrant.ts`, `kid/ProfilePickerPage.tsx`, `library/LibraryPage.tsx`, `reader/Reader.tsx` | Zoomed child-facing flow |
| Guardian + Admin Journey | [journey-guardian.puml](journey-guardian.puml) / [.svg](journey-guardian.svg) | `frontend/src/router.tsx`, `auth/AdultGate.tsx`, `guardian/LoginPage.tsx`, `ConsolePage.tsx`, `admin/AdminConsolePage.tsx`, `IntakePage.tsx`, `RequestsPage.tsx`, `BooksPage.tsx` | Zoomed parent + admin flow (approve is admin-only, ADR-005) |
| Journey Test Coverage | [journey-dev-coverage.puml](journey-dev-coverage.puml) / [.svg](journey-dev-coverage.svg) | `frontend/e2e/*.spec.ts` (Playwright), `frontend/src/**/*.test.tsx` (Vitest) | Journey recolored by e2e / unit / none coverage. The colours are a point-in-time snapshot re-verified by hand on 2026-08-04; no tool checks that date, and the diagram's own header carries the dated spec inventory. Per-element uncertainty belongs in a `<<unverified>>` stereotype ([STYLE_GUIDE.md](STYLE_GUIDE.md#status-stereotypes)), which an audit can actually find. |

## Maintenance

- Regenerate SVGs after editing any `.puml` with `python tools/generate_diagram_svgs.py`
  (or `--all` to force, `--check` to report staleness). See
  [STYLE_GUIDE.md](STYLE_GUIDE.md#regenerating-svgs).
- `--check` needs no PlantUML jar and is designed to run in CI, but nothing invokes it
  today: `grep -rn generate_diagram_svgs .github/ .pre-commit-config.yaml noxfile.py`
  returns nothing (re-verified 2026-08-14). Treat it as a command you run by hand, not a
  gate that will catch you. Wiring it into a workflow is the open follow-up.
- **Staleness is decided by git commit time, not filesystem mtime**, so an *uncommitted*
  `.puml` edit is invisible to both `--check` and the default render mode: both will
  report "up to date" and render nothing while your working tree disagrees with the
  committed SVG. This is deliberate (mtimes do not survive `git clone`, so an mtime gate
  is a no-op in CI), but it inverts the usual local workflow. Commit the `.puml` first,
  then run the tool, then amend the SVGs into that commit. `--all` is the alternative and
  re-renders all ~80 diagrams, including the `skeletons/` tree, for a much noisier diff.
- Rendering needs Graphviz on `PATH` for every component and deployment diagram; the
  activity and sequence diagrams render without it. Without `dot`, PlantUML writes an
  error-image SVG rather than failing, so a run that "succeeded" can still have committed
  a placeholder. Set `GRAPHVIZ_DOT=$(which dot)` if PlantUML looks in the wrong place
  (it defaults to `/opt/local/bin/dot`), and sanity-check output sizes before committing:
  an error placeholder is an order of magnitude smaller than the real diagram.
- Prefer naming a function over pinning a line number in a traceability note. Two pins in
  `component-generation.puml` (`orchestrator.py:492`, `import_story.py:541`) both went
  stale the moment Stage D shifted the file, and nothing flagged them, because a line
  number that still resolves to *some* line is not detectably wrong.
- The `Primary sources` column is a maintenance aid, not an exhaustive list; each
  `.puml` carries a full `' Source files:` traceability block. A source path that no
  longer exists is drift the diagram audit will flag.
