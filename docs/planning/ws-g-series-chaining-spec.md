---
schema_type: planning
title: "WS-G: Series Chaining Specification"
description: "Design spec for workstream G of the story lifecycle redesign: the full ADR-011
  series generation path. Populates the embedded Series metadata at generation, converges
  successful endings on the next book's series_entry_node via a declared runtime contract,
  carries name-matched variable state for higher bands, and wires the dormant SR-1..SR-7
  validator into release approval."
tags:
  - planning
  - series
  - specification
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Capture the ratified WS-G design (four owner-gated decisions plus the convergence
  contract, generation changes, validator wiring with the SR-4 relaxation and grandfather rule,
  continuation runtime, testing bar, and 3-PR split) so the implementation plan and build can
  proceed without re-deriving scope."
component: Generation
source: "docs/planning/story-lifecycle-redesign.md (umbrella, ratified 2026-07-06, Design section
  3 and decisions 4 and 5); ADR-011 section 8; docs/planning/ws-g-handoff-2026-07-09.md (branch
  docs/ws-ef-kickoff); codebase discovery 2026-07-09 against origin/main a9b1b06 (post WS-C PR2
  #175)."
---

## Overview

WS-G activates the series scaffolding that WS-B built and left dormant by design. After WS-G, a
series is a chained reading experience: every series book's document carries a populated embedded
`Series` metadata block, a kid who reaches a successful ending of a non-final book can continue
into the next book at its declared entry node with declared state carried across (higher bands
only), and the SR-1..SR-7 cross-book validator gates release approval instead of sitting unused.

Dependency gate (verified 2026-07-09): WS-C PR2 (#175) is merged; `generation/skeleton_match.py`
selects on (band, length, style) and `StorybookVersion.skeleton_slug` exists. Alembic head at
branch-cut is `228c68e8f1e7` (single head). WS-G adds **no migration** (section 7).

## Ratified decisions (2026-07-09)

All four were put to the owner as structured options and ratified. They are settled.

| # | Decision | Choice | Rationale |
| --- | --- | --- | --- |
| G1 | Convergence mechanism and reader scope | Declared metadata plus a reader-runtime continuation jump; the reader surface and a next-in-series API are in WS-G scope (own PR) | Book N is approved before book N+1 exists, so generation-time rewiring would mutate immutable approved blobs; without the reader surface chaining is invisible |
| G2 | Entry-node choice and population point | `series_entry_node` = the document's existing top-level `start_node`, for every series book; the embedded `Series` block is written by the generation worker in the same transaction that assigns `book_index` | Zero authoring burden, satisfies SR-3, works identically for skeleton-filled and fresh generation |
| G3 | State-carry contract (v1) | Name-matched variable seeding at the continuation jump, client-side; generation prompts for continuations instruct reuse of the anchor book's variable names via an extended `AnchorContext` | No DB or document schema change; reuses the existing client-originated `var_state` trust boundary |
| G4 | Validator wiring and SR-4 semantics | Relax SR-4 to ADR-011 prose semantics (only a non-top book being final is an error; open chains valid); run `validate_series` inside release approval for series books over the chain-so-far, blocking on SR errors; grandfather pre-WS-G chains | Open-ended series must validate without mutating approved blobs; approval is the natural cross-book choke point |

Two related questions from the handoff resolved without new decisions:

- **Episodic enforcement** was already settled in WS-B: `carries_state` is derived from the band at
  series creation (`story_requests/service.py:132`, False for `3-5`/`5-8`). WS-G consumes it; it
  does not re-derive it. Episodic series still chain reading order; they only skip state seeding.
- **is_final**: v1 writes `is_final=False` on every generated series book. Closing a series is a
  future feature, valid under the relaxed SR-4.

## 1. The convergence contract

Convergence is **declared, not wired**. Book N's node graph is never edited after approval.

- Every generated series book's document carries `StoryMetadata.series` populated with:
  `series_id` (from the storybook's series linkage), `book_index` (from the existing
  `link_series_position` assignment), `series_entry_node` (the document's `start_node`),
  `is_final=False`, and `carries_state` (copied from the `series` table row).
- The runtime contract: when a reader reaches an ending with `kind` in {SUCCESS, COMPLETION}
  (`validator/series.py::_SATISFYING_KINDS`) in a non-final series book, the reader MAY offer
  "Continue the series", which opens book N+1 at N+1's declared `series_entry_node`.
- SR-5 deliberately does not machine-check the cross-book target (books are independent graphs);
  this spec makes the runtime the explicit owner of that hop.

## 2. Generation path changes

In `generation/worker.py`, for jobs whose storybook has a `series_id`:

- `link_series_position` moves **before** blob serialization inside `_persist_and_moderate`, so
  the assigned `book_index` is available when the document is serialized. The existing savepoint
  retry guard on `uq_storybook_series_book_index` is reused untouched (`generation/series_link.py`;
  the umbrella's `#CRITICAL` concurrency race stays solved there, do not re-implement).
- The worker constructs the embedded `Series` block (fields per section 1) and writes it into the
  document before persisting the `StorybookVersion` blob. Non-series jobs are unchanged.
- Both the skeleton-fill path (`_run_skeleton_fill`) and fresh generation get the block; node ids
  survive skeleton fill 1:1 and every document has a top-level `start_node`, so G2 applies
  uniformly.

## 3. Validator wiring (SR gate at approval)

- **SR-4 relaxation** (`validator/series.py::_check_final_flags`): error only when a non-top book
  has `is_final=True`. The top-index book may be final or not (open-ended chains are valid). This
  matches ADR-011 section 8 prose ("only the top index may be is_final"); the current strict
  implementation would fail every open chain. Unit tests updated accordingly.
- **Wiring point** (`publishing/service.py::approve`): when the storybook being approved has a
  `series_id`, load the chain-so-far (each sibling series book's current published version blob,
  plus the version under approval), parse to `Storybook` models, and run `validate_series`. SR
  errors block approval (422 via the centralized exception hierarchy); the approval transaction
  rolls back. No new `pipeline_event` type; the existing `RELEASED` event is unchanged.
- **Grandfather rule**: if any OTHER published book in the chain lacks an embedded series block
  (pre-WS-G generation), skip the cross-book gate for that series and emit a structured warning
  log. Rationale: approved blobs are immutable (no backfill), and excluding legacy books would
  break SR-2 contiguity, so partial enforcement would produce false errors. Series whose books
  all carry the block get full enforcement.

## 4. Continuation runtime (reader plus API)

- **New kid-scoped endpoint** `GET /api/v1/reading/series-next` (profile id, storybook id):
  resolves the next book (sibling at `book_index + 1`) and returns its storybook id, published
  version, and declared `series_entry_node`, or a 200 with a null payload when there is no next
  book or it is not readable (expected absence is not an error). Readability reuses the existing child-read gate (published plus
  assignment/visibility, as widened by WS-E); this endpoint introduces no new access path.
- **Reader**: at a satisfying ending of a non-final series book, the reader queries series-next
  and, when readable, shows "Continue the series". v1 shows nothing otherwise (no
  ask-your-grown-up surface). On continue, the reader opens book N+1 with the machine initialized
  at the declared entry node rather than the default start (identical in v1 since entry =
  `start_node`, but the jump honors the declared field as the contract).
- **State seeding** (G3): when the completed book's `carries_state` is True, the reader seeds book
  N+1's initial `var_state` with the name-intersection of book N's final `var_state` and book
  N+1's declared `variables`. Episodic series skip seeding. Seeding is client-side: the reading
  state PUT already originates client-side, so carrying values across books adds no new trust
  boundary and no backend state-transfer surface.
- **OpenAPI impact**: one new route means client regeneration (`npm run generate-client`) and e2e
  updates in both `e2e/` and `e2e-real/` tiers ride in the same PR.

## 5. Generation-side continuity (state-export, v1)

- `AnchorContext` (`generation/concept.py`) gains the anchor book's declared variable names
  (from its blob's `variables`), alongside the existing title/character/ending-summary fields.
- Continuation prompts (series-anchored jobs) instruct the generator to reuse the anchor's
  variable names where the new story tracks the same state, which is what makes the name-matched
  intersection in section 4 land on real carryover for tier-2 books. Tier-1 books declare no
  variables; for them state carry is naturally a no-op regardless of band.
- The explicit declared-export block (variables annotated for export, validator-checked import)
  is the known v2 escalation if name matching proves too weak; it changes the document schema and
  is out of WS-G scope.

## 6. Error handling and edge cases

- Approval gate failures surface as structured 422s naming the SR rule ids; admins fix by
  regenerating or declining the book, never by editing approved blobs.
- series-next returns its null payload (200, not an error status) for: final book, no next book
  yet, next book unpublished, next book not readable by the profile.
- A continuation into a book whose reading state already exists (kid re-continues) must not
  clobber existing progress: seeding applies only when creating a fresh reading state for book
  N+1 (existing `state_revision` concurrency rules unchanged).
- Legacy chains (grandfathered) log a warning at approval; they gain enforcement only if every
  book in the chain is eventually regenerated with the block. No data mutation.

## 7. No migration, no new event types

The `series` table, `storybook.series_id`/`book_index` linkage, unique constraint, embedded
Pydantic `Series` schema, `ReadingState.var_state`, and `Completion` all exist. Every ratified
choice lands in existing columns, the immutable document blob, or the frontend. Alembic head
stays `228c68e8f1e7`; WS-G carries zero migration-collision risk with WS-E. No new
`pipeline_event` type is added.

## 8. Testing bar

- **Unit**: SR-4 relaxation (open chain valid, non-top final invalid); series-block construction
  (fields, entry = start_node, is_final False, carries_state copied); AnchorContext variable
  names.
- **Integration**: approval gate passes a valid chain, blocks an SR-violating chain, and
  grandfather-skips a chain containing a blockless legacy book; series-next resolution including
  the assignment/visibility gate; worker round-trip persisting the embedded block on both the
  skeleton-fill and fresh paths (and NOT on non-series jobs); book_index-before-serialize ordering
  under the existing concurrency test.
- **Frontend**: vitest for continue-visibility logic (satisfying ending, non-final, readable next)
  and var-state seeding (intersection, episodic skip, no-clobber); e2e chained-reading flow in
  both tiers.
- Standing gates: full backend suite with coverage >= 80 percent, ruff, basedpyright strict,
  bandit, OpenAPI drift gate (client regen in PR 2).

## 9. Delivery: three PRs, in order

| PR | Scope | Surfaces |
| --- | --- | --- |
| 1 | Embedded series block at generation (worker + persist ordering); SR-4 relaxation; approval gate + grandfather rule | Backend only; no client regen |
| 2 | series-next API; reader Continue + entry-node jump + var-state seeding; client regen; e2e both tiers | Backend route + frontend |
| 3 | Generation continuity: AnchorContext variable names + continuation prompt updates | Backend only |

PR 1 is the enforcement core and unblocks nothing downstream of WS-G; PR 2 makes chaining real
for readers; PR 3 improves carryover quality and can land last without blocking the others.

## Out of scope

- Closing a series (setting `is_final=True`) and any admin surface for it.
- Declared state-export blocks in the document schema (v2 escalation, section 5).
- An "ask your grown-up" continuation-request surface when the next book is not readable.
- Catalog-series branch notifications (umbrella open item, unresolved there).
- Any change to skeleton matching, moderation, thresholds, catalog, or dashboard surfaces.
