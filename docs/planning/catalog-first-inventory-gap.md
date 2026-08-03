---
title: "Process gap: catalog-first story inventory (admin authoring, guardian authorization, kid title requests)"
schema_type: planning
status: superseded
superseded_by: "src/cyo_adventure/db/models.py (CATALOG_FAMILY_ID sentinel, lines 56-71)"
owner: core-maintainer
purpose: "Record the ownership-model gap surfaced by the initial story-inventory run
  (stories require a family UUID at import), assess what the codebase already
  supports, and propose the catalog-first target model: admin-authored base
  inventory, guardian per-family authorization, and kid-initiated title requests."
tags:
  - planning
  - architecture
  - catalog
  - authorization
---

# Process gap: catalog-first story inventory

> **Status: SUPERSEDED (2026-07-28).** The "Gap A" fix proposed below, making
> `Storybook.family_id` nullable, was **rejected**. The shipped design instead
> owns catalog-origin content under a single fixed sentinel family,
> `CATALOG_FAMILY_ID = 0ca7a109-0000-4000-8000-000000000000`, so `family_id`
> stays a hard NOT NULL invariant everywhere and no family-scoped authz check
> had to be reworked for a null owner. The decision and its rationale are stated
> in code at `src/cyo_adventure/db/models.py` lines 56-71 (the authoritative
> source, not this doc). A catalog book still becomes globally visible only when
> an admin publishes it with `visibility='catalog'` (ADR-005 human approval
> unchanged), which is exactly requirement 2/3 of the gap below.
>
> **What actually resolved the gap** (verified 2026-07-28): the sentinel design
> was fully built and merged to `main`, and the 23 authored drafts were blocked
> by process rather than by any code or schema defect. See the disposition notes
> at the end of this file. This document is
> retained as the historical record of the rejected approach; do not implement
> Gap A as written.
>
> **Correction (2026-08-03).** The 2026-07-28 note above originally said the
> drafts "were blocked only because nobody had run the import command." That is
> not accurate as of its own writing date: issue #347, opened 2026-07-21, records
> an import run against production (the ADR-021 catalog seed, 25 stories landed
> at `in_review`). The import command had been run a week earlier. The blocked
> step is the one after it: `import_catalog.py` never publishes by design, and
> nothing on record shows the separate admin promotion,
> `publishing/catalog_publish.py::promote_catalog_story`, has run for this
> inventory. The gap's conclusion is unchanged, since an imported-but-unpromoted
> book is just as invisible to a kid profile as an unimported one; only the
> mechanism is corrected. Current live database state is not established by this
> document and is verified as step 1 of the SQ-01 runbook in
> [story-structure-implementation-briefs.md](story-structure-implementation-briefs.md).
>
> ---
>
> _Original proposal (2026-07-17), preserved for history:_ Surfaced during the
> initial story-inventory authoring run
> (`docs/planning/story-inventory-initial-run.md`), whose import step (section
> 8) requires `--family <uuid>`, which is wrong for a base inventory that no
> family owns.

## The gap, as stated

1. Stories should not require a family UUID; admins should author a base
   inventory that exists independent of any family.
2. Guardians should browse that inventory and decide which titles to authorize
   for their family.
3. Kids should be able to request a title from the main library, prompting
   their guardian to review it for inclusion.

## What the codebase already supports (investigated 2026-07-17)

The runtime is closer to this model than the authoring path suggests:

- **`Storybook.visibility` already exists** with the closed set
  `{family, catalog}` (WS-E decision E1/E5, PR #180;
  `publishing/state_machine.py::Visibility`). `catalog` "shares it with every
  family's guardian browse-and-assign surface", chosen by the ADMIN at release
  approval. `api/library.py` already honors catalog visibility cross-family on
  both the listing and direct-fetch paths.
- **Guardian authorization per family already exists**: guardians browse
  catalog books (`api/assignments.py::list_guardian_books`) and grant them per
  child via `StorybookAssignment`, which is the sole read-gate for what a
  child sees. This IS requirement 2, shipped.
- **The team anticipated catalog-origin flows**: deferred-debt item SL6 /
  issue #173 ("make `StoryRequest.family_id` nullable for catalog-origin
  requests") is already on the register.

## What is actually missing

- **Gap A (authoring/ownership)**: `Storybook.family_id` is NOT NULL
  (decision B3; the Series docstring notes "widening is WS-E"), and
  `generation/import_cli.py` requires `--family`. There is no admin/no-owner
  import path, so a "base inventory" story must be parked under some family
  even though `visibility=catalog` then shares it. The catalog concept exists
  at the SHARING layer but not at the OWNERSHIP layer.
- **Gap B (kid browse + title request)**: children can see ONLY assigned
  books; there is no kid-facing view of the main library and no way to
  request an existing title. `story_requests` is generation intake
  (free-text NEW-story requests, guardian-scoped in R1), not title requests
  of existing catalog books.

## Proposed target model

1. **Admin base inventory (Gap A)**: widen `Storybook.family_id` to nullable
   (a Supabase CLI SQL migration): NULL = library-owned, `created_by` records
   the admin. Add an import mode
   `import_cli <file> --library` (mutually exclusive with `--family`) that
   imports with no owning family; on admin release-approval these default to
   `visibility=catalog`. Family-scoped access checks treat NULL-owner rows as
   admin-managed (guardian surfaces already read catalog books cross-family,
   so most call sites need no change; the audit is enumerating every
   `family_id ==` filter that assumes NOT NULL).
2. **Guardian authorization (requirement 2)**: no change; the existing
   catalog browse + `StorybookAssignment` flow already implements it.
3. **Kid title requests (Gap B)**: a new, deliberately tiny surface:
   - Kid-facing "main library" browse: the catalog filtered to the profile's
     age band (title + cover + band only; no reader access), served on the
     kid surface next to "My library".
   - A `title_request` row (`child_profile_id`, `storybook_id`, `status`
     pending/approved/declined, timestamps): no free text, which keeps the
     COPPA/input surface unchanged.
   - Guardian console: a "Requested by your reader" queue; approve creates
     the `StorybookAssignment`, decline records status. Kid sees a gentle
     status chip. (This mirrors the existing story-request queue UX, so the
     frontend pattern is already established.)

## Interim unblock for the current 14-story inventory (no schema change)

Until Gap A lands, the run's deliverables can enter the database TODAY under
the existing model with 90% of the desired behavior:

1. Create one admin-owned "Library" family (a plain `family` row administered
   by the admin account).
2. `import_cli out/<slug>.filled.json --family <library-family-uuid>` for each
   of the 14 approved stories.
3. Approve each in the admin console and set `visibility=catalog` at release
   approval (the existing WS-E control).
4. Every real family's guardians can then browse and assign all 14 titles.

Only the kid-initiated title request (Gap B) has no interim equivalent; until
it ships, kids ask their guardian out-of-band, which matches R1's
guardian-mediated posture.

## Suggested sequencing

- **PR 1 (schema + import)**: nullable `family_id` migration + `--library`
  import mode + call-site audit + tests. Closes Gap A; supersedes the
  interim Library-family workaround (a backfill moves its rows to NULL owner).
- **PR 2 (kid requests)**: `title_request` table + 3 endpoints (kid create,
  guardian list/decide) + the two small frontend surfaces. Closes Gap B.
  Touches the OpenAPI contract, so regenerate the frontend client.
- Related cleanup to fold in: issue #173 (nullable `StoryRequest.family_id`
  for catalog-origin generation requests), same conceptual widening.

## Impact on the authoring-run plan

`story-inventory-initial-run.md` section 8's import command should be read
with this note: the `--family` requirement is the documented gap, and the
interim Library-family procedure above is the sanctioned path until PR 1
lands. Publication still requires ADR-005 human approval either way.

## Disposition (2026-07-28)

This section records how each thread above actually resolved, so the next
session does not re-derive it.

- **Gap A (nullable `family_id`): REJECTED, superseded by the sentinel.**
  Owning catalog content under `CATALOG_FAMILY_ID` (a permanent seed family)
  keeps `family_id` NOT NULL and leaves every family-scoped authz check
  untouched. Authoritative statement in `src/cyo_adventure/db/models.py`
  lines 56-71. The shipped, live tooling is `generation/import_catalog.py`
  (imports the authored drafts under the sentinel, never publishes) and
  `publishing/catalog_publish.py::promote_catalog_story` (per-story admin
  approval to `visibility='catalog'`). No `--library` import mode and no
  `family_id` migration were built or are needed.

- **`feat/catalog-first-admin-inventory` branch (the interim "Library family"
  workaround, PR #286): DELETED 2026-07-28, SUPERSEDED.** That branch
  (tip `d98137e`, recoverable from the reflog for roughly 90 days)
  implemented a third approach: an admin-owned "Library family" sentinel
  `00000000-0000-0000-0000-000000000001` plus `core/catalog.py` and migration
  `20260718000000_library_family.sql`. It was deleted rather than revived for
  two concrete reasons beyond simple redundancy. First, its migration version
  prefix `20260718000000` is already taken on `main` by
  `add_report_retention_purge.sql`, and Supabase keys
  `supabase_migrations.schema_migrations` on that prefix, so the two collide
  outright. Second, applying it anyway would seed a _second_ competing
  sentinel family that no code on `main` filters on, leaving an orphan
  "Library" row visible in `GET /families` (the exclusion at
  `api/families.py` filters only `CATALOG_FAMILY_ID`). Do not resurrect it.
  The one idea worth keeping is ergonomic, not structural: `import_cli.py`
  still has no `--catalog` convenience flag, so a single-file catalog import
  means typing the sentinel UUID by hand. Re-implement that fresh against
  current `import_cli.py` if wanted; do not cherry-pick, since `_run` has
  since gone keyword-only and gained `series_id`.

- **Issue #173 (nullable `StoryRequest.family_id`): resolved by the sentinel
  design.** Catalog-origin requests are owned by `CATALOG_FAMILY_ID` rather
  than a null owner, so the nullable widening #173 asked for is no longer
  wanted. The issue should be closed as superseded.

- **Gap B (kid-initiated title requests of existing catalog titles): still
  unbuilt, out of scope for the inventory-import work.** Children still see
  only guardian-assigned books; there is no kid-facing catalog browse or
  `title_request` surface. This remains a candidate for a future, deliberately
  tiny feature and is not required to make the authored drafts readable.
