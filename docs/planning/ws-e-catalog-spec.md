---
schema_type: planning
title: "WS-E: Catalog and Guardian Assignment Specification"
description: "Design spec for workstream E of the story lifecycle redesign: a Storybook visibility
  flag (family/catalog) set at release approval, guardian browsing and assignment of catalog books,
  and a server-side visibility check on assignment so a child is never assigned a book their
  guardian cannot see."
tags:
  - planning
  - specification
  - authorization
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Capture the WS-E design (proposed decisions plus the data model, approval and assignment
  changes, authorization contract, and testing bar) so the owner can ratify at kickoff and the
  implementation plan can proceed without re-deriving scope."
component: Strategy
source: "docs/planning/story-lifecycle-redesign.md (umbrella, ratified 2026-07-06, Design section
  7 and decisions 1 and 6); codebase discovery 2026-07-09 against main b15ed15."
---

## Overview

WS-E makes admin-approved books shareable to a global catalog that any guardian can assign from.
It adds a `visibility` axis to `Storybook` (`family` or `catalog`), chosen by the admin at release
approval and defaulting to `family`. Guardian book listing widens from own-family-only to
own-family plus catalog, and the assignment path grows a server-side visibility check so a child
can never be assigned a book their guardian is not entitled to see.

WS-E is full-stack (backend model + endpoints, frontend guardian browse and admin approval toggle,
both e2e tiers). Its only umbrella dependency is WS-B, which is merged, but see the dependency-gap
note under Proposed decision E4.

## Decisions (RATIFIED 2026-07-09)

E1 through E5 below were ratified by the owner as proposed at the WS-E kickoff on 2026-07-09 (the
umbrella's ten decisions remain settled and were not reopened). E4 ratified with the follow-up
tracked as issue #173 (make `StoryRequest.family_id` nullable for catalog-origin requests).

One additional coordination decision was ratified at kickoff:

- **E-mig (migration chaining)**: WS-C PR2 is concurrently in flight (branch
  `feat/ws-c-skeleton-matching`) with migration revision `228c68e8f1e7`
  (`20260709_0900_add_storybook_version_skeleton_slug.py`, `down_revision=b4c5d6e7f8a9`). The owner
  chose to chain WS-E's single migration onto `228c68e8f1e7` from the start, assuming WS-C PR2
  merges first. Consequence: WS-E's migration round-trip tests reference a revision not yet on
  main, so WS-E CI stays red on migrations until WS-C PR2 lands; merge order is WS-C PR2 then
  WS-E. If WS-C PR2 is abandoned or re-keyed, re-point WS-E's `down_revision` to the live head.

| # | Decision | Proposed choice | Rationale |
| --- | --- | --- | --- |
| E1 | `visibility` storage | New `visibility` column on `Storybook` (`String(16)`, CHECK `family`/`catalog`, `server_default='family'`), mirroring the `_STORYBOOK_STATUS_VALUES` + `CheckConstraint` pattern already on the table | Umbrella decision 1 and Design 7 put visibility on the book, chosen at approval. String+CHECK matches every other enum on `db/models.py`; server_default makes the migration safe for existing rows (all become `family`). |
| E2 | Where visibility is set | `visibility` is an argument to `publishing/service.py::approve`, supplied by the admin approval endpoint (`api/approval.py`), defaulting to `family` | `approve` already stamps the release fields; visibility is an approval-time decision (decision 1). Keeping it in `approve` keeps the release transition atomic and single-sourced. |
| E3 | Guardian catalog read model | `GET /api/v1/guardian/books` returns own-family published books plus all `visibility='catalog'` published books; response marks each item's `visibility` so the UI can badge catalog books | Decision 1 and Design 7: guardian library = family plus catalog. Badging lets the guardian tell shared books from their own without a second endpoint. |
| E4 | Admin catalog-request creation | **Descope for WS-E v1.** WS-E ships visibility-at-approval and catalog browse/assign only. Admin-initiated catalog requests with **no family** are NOT included, because `StoryRequest.family_id` is still non-nullable (WS-B delivered only nullable `profile_id`). File a WS-B follow-up to make `family_id` nullable before catalog-origin generation is built | The umbrella's "depends on B for admin catalog requests" premise is only half-satisfied (see Current-state gap). Shipping the visibility/browse/assign slice delivers the guardian-facing value without blocking on a request-model change; catalog-origin authoring becomes its own tracked unit. |
| E5 | Assignment visibility check | `assign_storybook` accepts a book that is either own-family OR `visibility='catalog'`; the existing cross-family 403 is replaced by "not (own-family or catalog) -> 403"; all other guards (published, foreign-profile) unchanged | Design 7: assignment works on anything visible, verified server-side. This is the security core of WS-E; it must be a server check, never a UI-only filter. |

## Current-state facts (verified 2026-07-09 against b15ed15)

- **`Storybook` ORM model**: `db/models.py:192` (`__tablename__="storybook"`). PK is `id: str`
  `String(120)` (NOT a `Uuid` PK; Storybook is the table-wide exception). Columns include
  `family_id` (Uuid FK, indexed), `current_published_version: int | None`, `status: str`
  (`String(20)`, default `draft`, CHECK `_STORYBOOK_STATUS_VALUES`/`ck_storybook_status`),
  `created_by`, `series_id`, `book_index: int | None`, `created_at`. There is a second
  `Storybook` at `storybook/models.py:458`, but that is the Pydantic content model, not the ORM
  row; WS-E edits the `db/models.py` one.
- **`visibility` does not exist yet** anywhere on the model. Confirmed.
- **`approved_by` and `published_at` live on `StorybookVersion`** (`db/models.py:255-258`), not on
  `Storybook`. The umbrella text implies they might be on the book; they are not. `visibility`,
  by contrast, belongs on `Storybook` (the book-level sharing decision), so E1 adds a new column
  rather than reusing a version field.
- **Release approval**: `publishing/service.py:111`,
  `async def approve(session, principal, storybook, version) -> StorybookVersion`. Stamps
  `storybook.status="published"`, `storybook.current_published_version=version`,
  `version_row.approved_by`, `version_row.published_at`, and records a `released` PipelineEvent
  in-transaction. It requires `in_review` state and a non-null moderation report. It is **not
  admin-only at the function level**; authorization is enforced at `api/approval.py`. E2 threads
  `visibility` through this function and its caller.
- **Guardian book listing**: `api/assignments.py:372`, `async def list_guardian_books(ctx)`, route
  `GET /api/v1/guardian/books`. Today filters strictly to
  `Storybook.family_id == ctx.principal.family_id`, `status=="published"`,
  `current_published_version IS NOT NULL`, and joined `StorybookVersion.approved_by IS NOT NULL`.
  Guardian-only (child and admin get 403). No catalog/cross-family concept exists yet.
- **Assignment**: `api/assignments.py:190`, `async def assign_storybook(storybook_id, body, ctx)`,
  route `POST /api/v1/storybooks/{storybook_id}/assignments`. Authorization runs through
  `_require_guardian_family_book`: guardian (403) -> missing book (404) -> cross-family (403) ->
  non-published (400) -> foreign profile (403). Writes are idempotent and emit one `book_assigned`
  event per newly created row. `StorybookAssignment` (`db/models.py:376`) is the child read gate
  (composite PK `(child_profile_id, storybook_id)`); `api/library.py` gates both listing and
  direct-version fetch on it. E5 relaxes only the cross-family check to a visibility check.
- **Current-state gap (dependency)**: `StoryRequest.family_id` is **NOT nullable**
  (`db/models.py:549`, `Mapped[uuid.UUID]`, no default). WS-B made only `profile_id` nullable
  (`db/models.py:550`). `initiator_role` exists (`'child'/'guardian'/'admin'`) so an
  admin-initiated request is representable, but a **family-less catalog request is not**. This is
  why E4 descopes catalog-origin request creation.
- **Migration head**: single clean head `b4c5d6e7f8a9`
  (`migrations/versions/20260709_1000_add_provider_model_allowlist.py`, WS-C PR1, #170). WS-E
  chains onto this (or the live head at branch-cut time; see coordination).
- **Frontend**: guardian/admin console pages live under `frontend/src/guardian/`
  (`ConsolePage.tsx`, `ReviewDetailPage.tsx`, `ModerationThresholdsPage.tsx`); there is no
  separate `src/admin/`. API adapters use the hand-typed `makeXApi(api: AxiosInstance)` pattern
  (`assignApi.ts`, `reviewApi.ts`, `coverApi.ts`, `moderationThresholdsApi.ts`); the generated
  `src/client/` is used for types by some adapters, never for requests.

## Data model

`Storybook` gains one column:

| Column | Type | Notes |
| --- | --- | --- |
| `visibility` | `String(16)`, CHECK (`family`/`catalog`), `server_default='family'`, not null | E1; `_STORYBOOK_VISIBILITY_VALUES` constant + `ck_storybook_visibility`, mirroring the existing status enum |

A `Visibility` Python `StrEnum` (`family`, `catalog`) is coerced at the application boundary, as
with the other string enums.

## Endpoint changes

- **`approve`** (`publishing/service.py`) and its caller `api/approval.py`: accept an optional
  `visibility` (default `family`), validate against the allowlist, set `storybook.visibility`, and
  include `visibility` in the `released` event payload (the event already carries `visibility` per
  the WS-D instrumentation map, so verify the value is now populated rather than defaulted).
- **`list_guardian_books`** (`api/assignments.py`): widen the query to
  `family_id == principal.family_id OR visibility == 'catalog'` (both still gated on published +
  approved). Add `visibility` to the response item shape so the UI can badge catalog entries.
- **`assign_storybook`** (`api/assignments.py`): in `_require_guardian_family_book`, replace the
  cross-family 403 with "book is neither own-family nor catalog -> 403". Keep the published and
  foreign-profile guards. This is the server-side enforcement of decision 1 and Design 7.

Any change to these endpoints or their response models changes the OpenAPI schema, so
`frontend/src/client/` must be regenerated in the same PR (CI drift gate; in-process dump, never
sort keys).

## Frontend

- Guardian library view (under `frontend/src/guardian/`) renders catalog books alongside family
  books with a visibility badge; assignment uses the existing assign adapter.
- The admin approval surface (`ReviewDetailPage.tsx`) gains a family/catalog choice at release,
  wired through the approval adapter.
- Adapters follow the hand-typed `makeXApi` house style; do not convert siblings to the generated
  client.

## Authorization and security

- The visibility check is server-side and authoritative (E5). A catalog book is assignable by any
  guardian; a family book only by its owning family. The UI badge is a convenience, never the gate.
- The admin approval UI carries the umbrella's reminder that catalog books must be free of personal
  details; that human gate is what the admin-gated catalog model relies on (Design 7).
- Threshold-style audit is not required for visibility, but the `released` event already records
  the chosen `visibility`, giving an audit trail through the pipeline log.

## Testing (umbrella bar)

- **Migration round-trip** with the pinned revision id via `tests/integration/_migration_utils.py`;
  assert existing rows default to `family`.
- **Contract test**: `list_guardian_books` returns catalog books from other families and own-family
  books, and never returns another family's `family`-visibility book.
- **Authorization test**: a guardian can assign a catalog book they do not own; a guardian cannot
  assign another family's `family`-visibility book (403); the child read gate is unchanged.
- **Approval test**: approving with `visibility='catalog'` sets the column and the `released` event
  payload; default approval yields `family`.
- **e2e**: update `frontend/e2e/guardian-books.spec.ts` and `assignments.spec.ts` for the catalog
  browse-and-assign flow; `library.spec.ts` and `guardian-console.spec.ts` may need touch-ups. The
  `e2e-real/` tier has no guardian-books or assignment specs today; add coverage only if the
  session decides the real tier needs it.

## Scope boundaries

- **In scope**: `visibility` column, approval-time setting, guardian catalog browse, assignment
  visibility check, the frontend for those, tests.
- **Out of scope (v1)**: admin-initiated **catalog-origin requests** with no family (blocked on the
  `StoryRequest.family_id` nullability gap, E4; tracked as issue #173); guardian-defined book groups
  by age and topic (umbrella says future phase); any re-moderation of existing books (visibility is
  orthogonal to moderation).

## Process

Signed commits (`git commit -S`), Conventional Commits, no em-dash characters (pre-commit hook),
CHANGELOG entry or skip-changelog label, owner-gated merge (never auto-merge), merge queue only.
Every new async DB function carries RAD markers per `src/cyo_adventure/CLAUDE.md`. Cycle: ratify the
proposed decisions above, then writing-plans for a task-level plan, then subagent-driven development
with per-task reviews and an Opus whole-branch review before the PR opens.
