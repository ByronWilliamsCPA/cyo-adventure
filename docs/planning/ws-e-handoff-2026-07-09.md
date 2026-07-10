---
schema_type: planning
title: "WS-E Kickoff Handoff: Catalog and Guardian Assignment (2026-07-09)"
description: "Session handoff to bootstrap the WS-E workstream: a Storybook visibility flag set at
  release approval, guardian catalog browse and assign, and a server-side visibility check on
  assignment, with verified current-state facts, a dependency-gap warning, and migration
  coordination."
tags:
  - planning
  - project
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Bootstrap a fresh session to run the WS-E spec, plan, and implementation cycle from the
  ratified umbrella, with the verified current-state facts, dependency gap, and migration
  coordination it cannot otherwise know."
component: Strategy
source: "docs/planning/story-lifecycle-redesign.md (umbrella, ratified 2026-07-06); WS-E spec
  docs/planning/ws-e-catalog-spec.md; codebase discovery 2026-07-09 against main b15ed15."
---

## Where things stand

WS-A (thresholds, #161/#162), WS-B (request lifecycle, #164/#165/#167), WS-D (pipeline event log,
#168), the book-covers feature (#169), and WS-C PR1 (per-job provider/model + admin allowlist,
#170) are all MERGED. Main is at `b15ed15` with a single clean Alembic head `b4c5d6e7f8a9`.

WS-E's only umbrella dependency is WS-B (merged), but that dependency is only half-satisfied: see
the dependency-gap warning below before planning admin catalog-request creation.

WS-C PR2 (band/length/style auto-vary skeleton matching) is NOT started and will likely add a
`skeleton_slug` provenance migration on `StorybookVersion`. Treat it as a concurrent migration
hazard (see coordination).

## Scope (from the umbrella and the WS-E spec)

Umbrella: `docs/planning/story-lifecycle-redesign.md`, Design section 7, decisions 1 and 6. The ten
umbrella decisions are settled; do not re-litigate them. The WS-E design detail lives in
`docs/planning/ws-e-catalog-spec.md`, which carries five PROPOSED per-WS decisions (E1-E5). Ratify
or override those at the start of this session before planning.

1. `Storybook.visibility` (`family`/`catalog`), set by the admin at release approval, default
   `family`.
2. Guardian library = own-family published books plus catalog published books; response badges
   visibility.
3. Server-side visibility check on assignment: a book is assignable if own-family OR catalog; the
   child read gate (`StorybookAssignment`) is unchanged.
4. Full-stack: backend model + three endpoint touch-points, frontend guardian browse + admin
   approval toggle, both e2e tiers as needed.

## Dependency-gap warning (read before planning)

The umbrella says WS-B made `StoryRequest.family_id` and `profile_id` nullable to support
admin-initiated catalog requests. **Verification against b15ed15 shows only `profile_id` is
nullable; `family_id` is still non-nullable** (`db/models.py:549`). `initiator_role='admin'` exists,
so an admin request is representable, but a family-less catalog-origin request is not.

The WS-E spec (decision E4) therefore DESCOPES catalog-origin request creation from v1: WS-E ships
visibility-at-approval plus catalog browse and assign only. If the owner wants catalog-origin
authoring in WS-E instead, that expands scope to include a `StoryRequest.family_id` nullability
migration and the generation path for family-less requests; raise it at kickoff. Otherwise file a
WS-B follow-up.

## Current state: touch-points (verified 2026-07-09, re-verify before building)

- `Storybook` ORM model: `db/models.py:192`, `String(120)` PK, `_STORYBOOK_STATUS_VALUES` + CHECK
  enum pattern to mirror for `visibility`. `visibility` does not exist yet.
- `approved_by`/`published_at` are on `StorybookVersion` (`db/models.py:255-258`), not `Storybook`;
  `visibility` is a new book-level column.
- Release approval: `publishing/service.py:111`
  `approve(session, principal, storybook, version)`; not admin-only at the function level (authz at
  `api/approval.py`); already records a `released` event whose payload includes `visibility`.
- Guardian listing: `api/assignments.py:372` `list_guardian_books`, `GET /api/v1/guardian/books`,
  family-scoped today.
- Assignment: `api/assignments.py:190` `assign_storybook`, `POST /api/v1/storybooks/{id}/assignments`,
  authz via `_require_guardian_family_book` (guardian -> missing -> cross-family -> non-published ->
  foreign-profile). Relax only the cross-family check to a visibility check.
- Frontend: guardian/admin pages under `frontend/src/guardian/`; hand-typed `makeXApi` adapters; no
  `src/admin/`.
- e2e: `frontend/e2e/guardian-books.spec.ts`, `assignments.spec.ts` (most on point), plus
  `library.spec.ts`, `guardian-console.spec.ts`. `e2e-real/` has none on this flow.

## Inherited obligations and constraints

- Any backend route or response-model change requires regenerating `frontend/src/client/` in the
  same PR (CI OpenAPI drift gate; in-process `app.openapi()` dump, never sort keys). WS-E DOES
  change public endpoints, so expect a real client diff.
- UI flows change, so both e2e tiers may need updates; state explicitly in the plan which specs are
  touched.
- Migration tests use `tests/integration/_migration_utils.py` with pinned revision IDs; assert
  existing rows default to `family`.
- Every new async DB function carries RAD markers per `src/cyo_adventure/CLAUDE.md`; the visibility
  check on assignment is a `#CRITICAL security` site.
- Repo process: signed commits, Conventional Commits, no em-dash characters, CHANGELOG entry or
  skip-changelog label, owner-gated merge, merge queue only.

## Migration and concurrent-session coordination

- **Worktree**: create `.worktrees/ws-e` and cut the branch from `origin/main` (never a local ref);
  run `uv sync --all-extras` in the worktree.
- **Head**: chain the single WS-E migration onto the live head at branch-cut time. As of
  2026-07-09 that is `b4c5d6e7f8a9`. Re-check with the head-detection recipe (the revision no other
  file names as its `down_revision`) before writing the migration; do not hardcode from this doc.
- **One-in-flight rule**: to preserve the owner's "single stable head, no re-chain" preference,
  only one migration-adding branch (WS-E, WS-F, or WS-C PR2) should be open at a time. If two are
  unavoidably in flight, the second merger re-points its `down_revision` to the first's head, the
  same drill covers/WS-D used. Keep WS-E to a single migration revision to make any such bump
  trivial.
- **File overlap**: WS-F touches `api/moderation_thresholds.py` and the events layer, not the
  assignment/publishing files WS-E edits, so E-vs-F code conflicts are unlikely outside
  `CHANGELOG.md`. WS-C PR2 edits generation/skeleton files, also disjoint from WS-E.

## Process expectation

Same cycle as WS-A/B/C/D: ratify the E1-E5 proposed decisions (one at a time or as a batch), commit
the ratified spec, then writing-plans for a task-level plan, then subagent-driven development with
per-task reviews and an Opus whole-branch review before the PR opens. WS-E is plausibly a single PR
(one column, three endpoint edits, guardian UI, tests); decide during planning.

## Kickoff prompt for the new session

"Run WS-E (catalog and guardian assignment) from the umbrella at
docs/planning/story-lifecycle-redesign.md, using the spec at docs/planning/ws-e-catalog-spec.md and
the handoff at docs/planning/ws-e-handoff-2026-07-09.md (absolute:
/home/byron/dev/CYO_Adventure/docs/planning/ws-e-handoff-2026-07-09.md). Work in .worktrees/ws-e cut
from origin/main. Start by ratifying the proposed E1-E5 decisions with me, then proceed to
writing-plans. Note the dependency-gap warning about StoryRequest.family_id before planning any
catalog-request-creation work."
