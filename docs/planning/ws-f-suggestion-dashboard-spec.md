---
schema_type: planning
title: "WS-F: Moderation Suggestion Dashboard Specification"
description: "Design spec for workstream F of the story lifecycle redesign: an admin dashboard that
  aggregates stored per-version moderation reports plus the pipeline_event log into
  moderation-threshold suggestions and lets an admin ratify a suggestion, which writes to the
  threshold table through the existing audited path. No auto-calibration. Decisions F1-F5 ratified
  2026-07-09."
tags:
  - planning
  - specification
  - moderation
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Capture the ratified WS-F design (decisions F1-F5 plus the aggregation model,
  ratify-apply flow, endpoints, and testing bar) so the implementation plan can proceed without
  re-deriving scope."
component: Moderation
source: "docs/planning/story-lifecycle-redesign.md (umbrella, ratified 2026-07-06, Design section
  6 and decision 3); WS-A thresholds and WS-D event log; codebase discovery 2026-07-09 against main
  b15ed15; F1-F5 owner-ratified 2026-07-09 (F1 revised to the hybrid report-plus-events source
  after code verification, see the F1 row)."
---

## Overview

WS-F is the learning loop's read side. It aggregates the stored per-version moderation reports
(`storybook_version.moderation_report`) together with the append-only `pipeline_event` log (WS-D)
into evidence about how age-band moderation thresholds are performing, proposes threshold
adjustments, and lets an admin ratify a proposal. A ratified change writes to the
`moderation_threshold` table through the existing WS-A admin-edit path, so it applies without a
deploy (umbrella decision 3) and inherits that path's audit trail and `threshold_changed` event.
**There is no auto-calibration, ever**; every change is admin-ratified.

WS-F depends on WS-A (threshold table and editor) and WS-D (event log), both merged. It is
full-stack (admin aggregation endpoints plus an admin dashboard page) and, under the ratified
decisions, adds **no migration and no new event type**.

## Decisions (owner-ratified 2026-07-09)

Ratified at the WS-F kickoff session. F1 was revised from the originally proposed events-only
source after code verification showed that proposal was not implementable (see the F1 row and the
corrected current-state facts below). The ten umbrella decisions remain settled.

| # | Decision | Ratified choice | Rationale |
| --- | --- | --- | --- |
| F1 | Override signal source | **Hybrid report-plus-events**: per-finding `category`/`verdict`/`score` comes from the persisted final report on `storybook_version.moderation_report`, the age band from the version blob's typed metadata (`metadata.age_band`), and the outcome from the storybook's `released` vs `sent_back` events, attributed to a version by event-time ordering (see current-state facts). "Released despite a category-X advisory in band B" is the override proxy | The originally proposed events-only source assumed the `moderation_completed` payload carries per-category counts; it does not (and by the WS-D D3 PII contract it never can, a `#CRITICAL` marker in `moderation/pipeline.py` forbids `category` in the payload because provider categories are provider-derived strings). The persisted report retains full per-finding granularity, so the hybrid keeps the umbrella's per-(band, category) example, stays compute-on-read, and needs no migration and no new event type. Known coarseness, accepted eyes-open: a release overrides ALL advisories on that version at once, so co-occurring categories share the override credit. A dedicated per-finding override event remains a WS-D follow-up if the proxy proves too coarse. |
| F2 | Suggestion persistence | **Compute-on-read**: suggestions are computed live from events per request; no suggestions/proposals table | v1 data volumes are small; live aggregation avoids a new table, a new lifecycle, and a migration. Persisting proposals (with dismissed/accepted state) is a later concern if the list grows. |
| F3 | Ratify-apply path | A ratified suggestion calls the **existing** `PUT /api/v1/admin/moderation-thresholds/{age_band}` upsert path; WS-F adds no second write path to the threshold table | Reuses the WS-A audit table (`moderation_threshold_audit`) and the already-instrumented `threshold_changed` event for free; keeps a single source of truth for threshold writes; satisfies "applies without a deploy" and "changes are evented." |
| F4 | Suggestion scope v1 | **Threshold suggestions only.** Prompt-adjustment suggestions are deferred (umbrella open item: they may need more data) | Matches the umbrella's stated v1 boundary; threshold suggestions have a clean apply target (the threshold table), prompt suggestions do not yet. |
| F5 | Surface | New admin-only read endpoints under a dashboard router (proposed `GET /api/v1/admin/moderation/dashboard` for aggregates and `GET .../suggestions` for proposals); ratify reuses the WS-A PUT. Admin dashboard page under `frontend/src/guardian/`, alongside `ModerationThresholdsPage.tsx` | Keeps aggregation read-only and admin-gated; slots into the existing console; ratify has no new write surface (F3). |

## Current-state facts (verified 2026-07-09 against b15ed15)

- **`PipelineEvent`**: `db/models.py:709`, append-only (DB `BEFORE UPDATE OR DELETE` trigger).
  Columns include `occurred_at`, `actor_id`/`actor_role`, `entity_type` (`String(32)`, CHECK vocab
  `_PIPELINE_ENTITY_TYPE_VALUES` including `moderation_threshold`, `moderation_setting`,
  `storybook_version`), `entity_id` (`String(255)`), `event_type` (`String(48)`, CHECK), `payload`
  (JSONB, not null). `EventType` (`events/models.py:41`) has 14 values including
  `moderation_completed`, `released`, `sent_back`, `threshold_changed`, `noise_floor_changed`.
- **Event writer**: `events/writer.py:86`
  `record_event(session, actor, *, entity_type, entity_id, event_type, from_state=None, to_state=None, payload=None)`;
  validates the payload against a per-event allowlist and `flush()`es in the caller's transaction.
- **`moderation_completed` payload has NO category dimension** (correction to the original draft of
  this spec): the emit site (`moderation/pipeline.py`, `_verdict_counts`) writes only
  `overall_verdict` (block/flag/pass), `repaired` (bool), and `counts` keyed by **verdict**
  (block/flag/advisory/pass). A `#CRITICAL` security marker forbids a finding's `category`,
  `message`, or `node_id` from entering the durable payload (WS-D D3), so events alone can never
  yield per-(band, category) rates.
- **Per-finding data survives on the version row**: `StorybookVersion.moderation_report`
  (`db/models.py:252`, JSONB, nullable) stores the final `ModerationReport.to_dict()` with each
  finding's `category`, `verdict`, and `score`. The age band comes from the version blob's typed
  metadata (`story.metadata.age_band`, see `moderation/pipeline.py:318`), so no request-table join
  is needed.
- **Outcome events are per-storybook, not per-version** (second correction to the original draft):
  `released` and `sent_back` are emitted with `entity_type="storybook"` and plain
  `entity_id=storybook.id` (`publishing/service.py`, from_state `in_review`). Only
  `moderation_completed` uses `entity_type="storybook_version"` with
  `entity_id = f"{story_id}:{version}"`. Version attribution therefore orders events in time: a
  version's outcome is the first `released`/`sent_back` event on its storybook at or after that
  version's `moderation_completed` event. Versions with no subsequent decision event are undecided
  and excluded from the override-rate denominator (with `approved_by IS NOT NULL` on the version
  row accepted as a released signal for pre-WS-D history that has no events).
- **Threshold table + API**: `ModerationThreshold` (`db/models.py:591`; unique `(age_band, category)`,
  `min_verdict`, `min_score`), `ModerationThresholdAudit` (`db/models.py:653`, action
  `upsert`/`delete`, old/new values, `changed_by`), `ModerationSetting` (`db/models.py:766`, single
  `admin_noise_floor` row). Endpoints in `api/moderation_thresholds.py`, all `_require_admin`:
  `list_thresholds` (GET), `upsert_threshold` (PUT `.../{age_band}`, category via query param),
  `delete_threshold` (DELETE), `get_noise_floor`/`update_noise_floor`.
- **Threshold changes are already evented**: `upsert_threshold` and `delete_threshold` emit
  `threshold_changed`; `update_noise_floor` emits `noise_floor_changed` (WS-D instrumentation).
  So the ratify-apply path (F3) produces its audit event automatically, and the dashboard can also
  aggregate the change history itself.
- **v1 threshold seed**: WS-A shipped zero override rows; the code default (surface `flag` and
  above) applies to every band and category. Per-band overrides are expected to come from exactly
  this dashboard's evidence (umbrella Design 5).
- **Migration head**: single clean head `b4c5d6e7f8a9` (WS-C PR1, #170). Under F1/F2, WS-F adds no
  migration.
- **Frontend**: admin/guardian pages under `frontend/src/guardian/`
  (`ConsolePage.tsx`, `ModerationThresholdsPage.tsx`); hand-typed `makeXApi` adapters
  (`moderationThresholdsApi.ts` reuses generated types); no `src/admin/`.

## Aggregation model

Read-only queries over `storybook_version` (per-finding report and band) correlated with
`pipeline_event` (outcomes and change history; indexes exist on `(entity_type, entity_id)`,
`event_type`, `occurred_at`). Ratified v1 aggregates:

- **Override rate per (age_band, category)** (F1 hybrid): of the versions whose persisted
  `moderation_report` contains a category-C finding at an advisory verdict for a book in band B
  (band from the blob's `metadata.age_band`), the fraction whose storybook subsequently emitted
  `released` (not `sent_back`) in the event log, attributed per version by event-time ordering
  (undecided versions excluded from the denominator). A high rate suggests the advisory
  threshold for (B, C) is too aggressive and is a candidate to raise. Accepted coarseness: a
  release counts as an override for every advisory on that version. The same coarseness extends
  across versions: if an intermediate version has no decision event of its own, the first later
  decision on the storybook (typically the eventual release) is attributed to it as well.
- **Volume and recency**: counts and last-seen per (band, category) so a suggestion carries a
  confidence signal and is not proposed on a handful of samples.
- **Threshold-change history**: recent `threshold_changed` / `noise_floor_changed` events, so the
  dashboard shows what has already been adjusted.

The aggregation reads finding `category`/`verdict`/`score` values and band enums server-side under
admin auth; only counts, rates, ids, and enum values cross the API boundary, never finding messages
or story prose, preserving the WS-D D3 posture at the API surface. Where a human needs the
underlying book, the dashboard links to the existing admin review surface under admin auth.

## Suggestion and ratify flow

1. `GET .../moderation/dashboard` returns the aggregates above.
2. `GET .../moderation/suggestions` returns computed proposals: for each (band, category) whose
   override rate and volume clear a threshold, a proposal to raise `min_verdict` (or set `min_score`)
   with the supporting numbers.
3. The admin reviews a proposal and clicks apply, which calls the existing
   `PUT .../admin/moderation-thresholds/{age_band}` (F3). That write upserts the threshold, writes a
   `moderation_threshold_audit` row, and emits a `threshold_changed` event, all already built.
4. No proposal is ever applied automatically (decision 3). Dismiss is a no-op in v1 (compute-on-read,
   F2); the proposal simply stops appearing once the threshold moves.

## Endpoints

- `GET /api/v1/admin/moderation/dashboard` (admin-only): aggregates.
- `GET /api/v1/admin/moderation/suggestions` (admin-only): computed proposals.
- Apply reuses `PUT /api/v1/admin/moderation-thresholds/{age_band}` (existing, admin-only).

New GET endpoints change the OpenAPI schema, so regenerate `frontend/src/client/` in the same PR
(drift gate; in-process dump, never sort keys).

## Frontend

- New admin dashboard page under `frontend/src/guardian/` (proposed `ModerationDashboardPage.tsx`),
  routed alongside `ModerationThresholdsPage.tsx` in `routes.ts`/`App.tsx`.
- A hand-typed `makeDashboardApi` adapter for the two GETs; apply reuses the existing thresholds
  adapter so the audited write path is shared.
- Show each suggestion with its supporting numbers and an apply control; make it obvious that apply
  is a human ratification, not automation.

## Error handling and security

- All read endpoints are `_require_admin`; guardians and children get 403.
- Aggregation is read-only; the only write is the reused, audited threshold upsert.
- No PII crosses the boundary: event payloads are already PII-free; the dashboard surfaces counts,
  rates, ids, and enum values only.

## Testing

- **Aggregation correctness**: seed a fixture set of `storybook_version` rows (blob metadata band +
  `moderation_report` findings) with correlated `released`/`sent_back` events and assert the
  computed override rate, volume, and recency per (band, category), including the
  co-occurring-categories case (one release credits every advisory on the version).
- **Suggestion logic**: assert a proposal appears only above the volume/rate thresholds and proposes
  the correct `min_verdict`/`min_score` change.
- **Ratify path**: applying a suggestion upserts the threshold, writes an audit row, and emits a
  `threshold_changed` event (reuse the WS-A tests as the template).
- **Authorization**: non-admin roles get 403 on both GETs.
- **Frontend**: dashboard renders suggestions and wires apply through the shared thresholds adapter
  (Vitest + Testing Library). e2e only if the session decides the console flow needs a real-tier
  spec.

## Scope boundaries

- **In scope (v1)**: read-only aggregation endpoints, computed threshold suggestions, admin ratify
  via the existing threshold upsert, the dashboard page, tests. No migration, no new event type
  (F1/F2).
- **Out of scope (v1)**: prompt-adjustment suggestions (F4, deferred); a persisted
  suggestions/proposals table with dismissed/accepted state (F2, later if needed); a dedicated
  per-finding override event in the WS-D taxonomy (F1 follow-up if the released-despite-flag proxy
  is too coarse); any auto-calibration (forbidden by decision 3).

## Process

Signed commits (`git commit -S`), Conventional Commits, no em-dash characters (pre-commit hook),
CHANGELOG entry or skip-changelog label, owner-gated merge (never auto-merge), merge queue only.
Every new async DB function carries RAD markers per `src/cyo_adventure/CLAUDE.md`. Cycle: decisions
ratified 2026-07-09 (above), then writing-plans for a task-level plan, then subagent-driven
development with per-task reviews and an Opus whole-branch review before the PR opens.
