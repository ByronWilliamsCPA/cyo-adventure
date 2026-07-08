---
schema_type: planning
title: "WS-B: Request Lifecycle Redesign"
description: "Workstream spec for the enriched story-request lifecycle: new request fields, three
  initiator flows, the brief derivation flip, and series tagging with soft continuation."
tags:
  - planning
  - architecture
  - story-requests
  - series
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Record the ratified WS-B design so the implementation PRs can be planned and executed
  against a settled spec, beneath the umbrella decisions in story-lifecycle-redesign.md."
component: Strategy
source: "Brainstorming session 2026-07-08 (Fable 5); current-state re-verification of
  story_requests, generation brief, moderation threshold context, series validator, and frontend
  request/approval surfaces on main at 9b43d63."
---

## Scope

WS-B from the umbrella (`docs/planning/story-lifecycle-redesign.md`, Design sections 1 and 3):
new `StoryRequest` fields, three initiator flows with skipped redundant approvals, the brief
derivation flip (request becomes the source of truth for band and length), and series tagging
(table plus request-time anchoring) with soft continuation. Full-stack: backend, contract, and
all three initiator-flow UIs.

The ten umbrella decisions are ratified and not revisited here. This spec adds the
workstream-level decisions ratified 2026-07-08:

| # | Decision | Choice |
| --- | --- | --- |
| B1 | UI scope | Full-stack workstream; all three initiator-flow UIs ship in WS-B |
| B2 | Continuations before WS-G | Soft continuation: generate now with anchor-derived brief context; DB-level series linkage only; no embedded Series metadata, so SR-1..SR-7 do not fire |
| B3 | Admin no-family requests | Deferred to WS-E. Admin-initiated requests require a family; `story_request.family_id` and `series.family_id` stay NOT NULL in WS-B |
| B4 | PR decomposition | Three vertical slices (below); main deployable after every merge |

## Non-goals

- Skeleton matching stays band-only. `length` and `narrative_style` are recorded on the request,
  brief, and job metadata but do not affect skeleton selection until WS-C. Do not wire them in
  early.
- No entry-node convergence, state carry, or embedded `Series` document metadata (WS-G).
- No catalog visibility, no-family requests, or catalog anchors (WS-E).
- No `pipeline_event` instrumentation (WS-D).

## Current state (verified 2026-07-08 on main at 9b43d63)

- `StoryRequest` (`src/cyo_adventure/db/models.py:340-405`) carries `request_text` plus
  non-nullable `family_id`/`profile_id`; statuses `pending/approved/declined/blocked` in a CHECK
  constraint.
- Brief derivation reads the profile: `brief.py:69` (`AgeBand(profile.age_band)`), signature
  `brief_from_request(request_text, profile)`.
- The WS-A moderation flag context also reads the joined profile band
  (`api/story_requests.py:315,344,348`), so the flip touches moderation surfacing.
- Series is Pydantic-only (`storybook/models.py:180-204`); SR-1..SR-7 exist in
  `validator/series.py`; no DB table, no tagging path.
- Approval (`story_requests/service.py:73-139`) builds the Concept and sets
  `status = "approved"`; no GenerationJob is created there.
- Migration head: `c9d0e1f2a3b4`.
- Frontend surfaces: kid `frontend/src/library/RequestStory.tsx`, guardian
  `frontend/src/guardian/RequestsPage.tsx` (approve/decline queue with a double-click guard).

## Design

### 1. Data model

PR 1 migration (chains onto `c9d0e1f2a3b4`), all on `story_request`:

- `initiator_role` text NOT NULL, CHECK `('child','guardian','admin')`, server default `'child'`
  (also the backfill for existing rows; the kid flow is the only creation path today).
- `age_band` text NOT NULL, CHECK against the frozen band literals (WS-A
  `ck_moderation_threshold_age_band` pattern: enum-derived in the ORM, frozen literals in the
  migration). Backfilled from the joined child profile. NOT NULL is safe because every creation
  path sets it: the child flow stamps it from the profile server-side; guardian and admin flows
  require it at creation.
- `length` text nullable, CHECK `('short','medium','long')`. Null means the guardian has not set
  it yet; the approve endpoint enforces presence. Historical approved rows keep null harmlessly:
  brief derivation only runs at approval, so they never re-enter the flipped path.
- `narrative_style` text NOT NULL default `'prose'`, CHECK `('prose','gamebook')`, plus a
  cross-column CHECK: `narrative_style = 'prose' OR age_band IN ('13-16','16+')` (ADR-011's band
  rule enforced in the database).
- `profile_id` becomes nullable. `family_id` stays NOT NULL (decision B3; widening is WS-E).

PR 3 migration:

- New `series` table: `id`, `title`, `family_id` (NOT NULL, decision B3), `created_by`,
  `carries_state`, `age_band`, `created_at`.
- `story_request` gains `series_id` (nullable FK), `anchor_storybook_id` (nullable FK), and
  `proposed_series_title` (nullable text). A kid proposal is only a title until the guardian
  ratifies it; declined requests leave no orphan series rows.
- `storybook` gains `series_id` (nullable FK) and `book_index` (nullable int) with UNIQUE
  `(series_id, book_index)`. That constraint plus retry-on-conflict in the service layer is the
  umbrella's ratified concurrency guard.
  `#CRITICAL: concurrency: two continuations of the same series racing on book_index`
  `#VERIFY: unique constraint plus one retry on conflict; concurrency test in PR 3`

Series linkage is DB-columns-only in WS-B. The embedded Pydantic `Series` block is not written
into the storybook document, so SR-1..SR-7 never fire on soft continuations. WS-G starts
embedding it when structural chaining arrives.

### 2. API contract and initiator flows

- Kid create (existing endpoint; extended only in PR 3): stays minimal. `request_text` plus,
  in PR 3, optional `proposed_series_title` or `anchor_storybook_id`. Kids never set band,
  length, or style; band is stamped from the profile server-side. PII and blocked screening
  unchanged.
- Guardian approve (PR 1, breaking): approval requires `age_band` (prefilled from the request,
  confirmable) and `length`; accepts `narrative_style`, rejecting `gamebook` below band 13-16
  with 422. Missing band or length: 422. In PR 3 it gains series confirm/edit: ratify the kid's
  proposal (create the `series` row, set `series_id`), edit the title, or remove it.
- Guardian create (PR 2, new): guardian-scoped; `profile_id` optional; band, length, style, and
  (PR 3) series set at creation; row created in `approved` status with
  `initiator_role='guardian'`, straight to the admin queue. Screening still runs; a
  guardian-initiated request can still be blocked.
- Admin create (PR 2, new): admin-only; family required (decision B3); otherwise mirrors
  guardian create with `initiator_role='admin'`.
- Statuses, decline, and the blocked path are untouched.

### 3. Derivation flip (PR 1, highest risk, lands first)

- `brief_from_request()` takes the `StoryRequest` row and reads `age_band`, `length`, and
  `narrative_style` from it. The `ChildProfile` parameter becomes optional, kept only for
  non-band personalization; profile-less requests pass None and get a neutral brief.
- `GenerationBrief` gains `length` and `narrative_style` fields (recorded, not yet used for
  skeleton selection; see Non-goals).
- The moderation flag context switches from the joined `ChildProfile.age_band` to
  `StoryRequest.age_band`. The PR 1 backfill copies from that same join, so the switch is
  behavior-identical for existing data; WS-A threshold surfaces cannot shift retroactively.
- `approve_story_request()` builds the `ConceptBrief` from request fields and stamps the
  guardian's confirmed band and length back onto the request row before the status transition.
- `#CRITICAL: data integrity: brief and moderation band reads assume the backfill covered every
  historical row` `#VERIFY: migration round-trip test asserts post-upgrade band equals the
  profile band for all pre-existing rows`

### 4. Series tagging and soft continuation (PR 3)

- Creating: kid proposes via `proposed_series_title`; guardian ratifies at approval, creating
  the `series` row (`age_band` copied from the request; `carries_state` from ADR-011's band
  rule: episodic for 3-5 and 5-8, carry for higher bands). Guardian- and admin-initiated
  requests are pre-approved and may create the series row directly at creation.
- Continuing: `anchor_storybook_id` must reference a series-linked storybook in the requester's
  family. Validated at creation and re-validated at approval: anchor exists, is published, and
  its series band matches the request band. Continuations inherit `age_band` from the series;
  approval rejects a mismatch rather than silently forking the series.
- Soft continuation: the brief gains an `anchor_context` block extracted from the anchor
  storybook's document (title, main character names, a short summary of how it ended) so the
  generated book follows on thematically.
- `book_index` is assigned once, at generation completion, when the storybook row is created:
  `max(book_index) + 1` under the UNIQUE constraint with one retry on conflict. Assigning at
  request time would leave holes from declined or failed requests.

### 5. Frontend

- PR 1: the guardian approve action in `RequestsPage.tsx` becomes a confirm step with band
  (prefilled), length, and style selects; style renders only for bands 13-16 and 16+, defaulting
  to prose. The existing double-click guard carries over. Ships with the backend contract change
  so the deployed queue never breaks.
- PR 2: a guardian "Request a story" form (child selector optional; band, length, style pickers;
  band prefilled when a child is chosen). The admin variant lives on the existing admin console
  area of the same surface (one-door design, no `/admin` route) and adds the required family
  selector.
- PR 3: kid `RequestStory` gains an optional series-title field and a "continue this story"
  entry point from a series-tagged book in the kid library (pre-fills `anchor_storybook_id`);
  the guardian approve dialog gains the series confirm/edit control.
- The generated API client is regenerated in every PR via the in-process schema dump
  (`OPENAPI_INPUT=<file> npm run generate-client`), the same path the CI drift gate uses.

### 6. Testing and security

- Migration round-trips with pinned revision IDs for both migrations, using the shared
  `tests/integration/_migration_utils.py` helpers (PR #163), including the backfill assertion
  and CHECK rejection matrices (bad role, bad band, gamebook below band 13-16).
- Contract tests: approve without band or length yields 422; gamebook for low bands yields 422;
  each initiator flow's created status and `initiator_role`; authorization matrix (kid cannot
  set band; guardian cannot create admin requests; guardian create scoped to own family);
  flag-threshold tests re-pinned to the request-sourced band.
- Concurrency test (PR 3): two simulated completions racing on the same series must produce
  distinct `book_index` values via the retry path.
- Anchor validation tests: cross-family anchor, unpublished anchor, and band mismatch all
  rejected.
- e2e updates in both `e2e/` and `e2e-real/` tiers in every PR that changes a flow.
- All new write endpoints role-gated through the existing dependency chain; no free-form enum
  strings reach the DB (CHECK constraints plus Pydantic literals); screening runs for every
  initiator; series titles are length-capped and screened like request text.

## PR decomposition (decision B4)

| PR | Name | Contents |
| --- | --- | --- |
| 1 | Enriched child flow | Migration (new columns, nullable `profile_id`, CHECKs, backfill), derivation flip, strict approve contract, guardian approve UI |
| 2 | Guardian and admin creation | New create endpoints and flows, guardian create form, admin create form |
| 3 | Series tagging and soft continuation | `series` table migration, request-time tagging and anchoring, anchor context in brief, `book_index` assignment, kid and guardian series UI |

Each PR is independently releasable; PR 1 lands first because the derivation flip is the
highest-risk change and benefits from the smallest possible diff.

## Handoff notes for implementation planning

- Treat code blocks in this spec as intent, not verified implementation; re-read the touched
  files before encoding contracts (lesson from WS-A: plan defects get copied verbatim into PRs).
- Regenerate the OpenAPI client in the same PR as any schema change; the drift gate enforces it.
- WS-E inherits: `family_id` widening on `story_request` and `series`, catalog anchors,
  no-family admin requests. WS-C inherits: length/style participation in skeleton matching.
  WS-G inherits: embedded `Series` metadata, SR enforcement in the pipeline, entry-node
  convergence, state carry.
