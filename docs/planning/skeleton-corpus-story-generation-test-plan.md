---
title: "Skeleton Corpus Story-Generation Test Plan"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Validate every committed skeleton in skeletons/ by actually filling it with prose and persisting the result to the dev database across each real authoring path, not just passing the structural gate."
tags:
  - planning
  - testing
  - skeleton-library
  - content-pipeline
component: Content-Pipeline
source: "docs/planning/skeleton-authoring-handoff.md; docs/planning/skeleton-library-expansion-plan.md; src/cyo_adventure/generation/skeleton_match.py; src/cyo_adventure/story_requests/authoring_plan.py; src/cyo_adventure/generation/import_cli.py; src/cyo_adventure/generation/import_story.py; src/cyo_adventure/generation/orchestrator.py; src/cyo_adventure/generation/persistence.py; src/cyo_adventure/moderation/pipeline.py; .claude/skills/cyo-author"
---

## Why this doc exists

`run_gate()` proves a skeleton is **structurally** sound (node budgets, reachability,
ending/decision floors, words-per-node walls). It does not prove that a skeleton can
actually be **authored** end to end: that its `<<FILL ...>>` directives can be turned
into real prose, that the filled story still passes the gate, that it clears (or
correctly trips) moderation, and that it lands in the database as a readable
`Storybook` row. The gate is a necessary but not sufficient check. `main` now carries
18 `production_eligible: true` skeletons across all 6 bands (see
[skeleton-library-expansion-plan.md](skeleton-library-expansion-plan.md), now
superseded/completed) and 3 non-production MVP seeds; none of them has been proven
through a real prose-fill + persist + moderate cycle as a corpus. This plan is that
proof pass.

## Corpus under test

Enumerate live rather than hardcode a list here (the corpus grows independently of
this doc): `skeletons/<band>/<slug>.json`, 21 files as of 2026-07-10 (re-verify at
landing time). The generated,
always-current table is the band-coverage matrix in
[docs/architecture/story-skeletons.md](../architecture/story-skeletons.md) (rebuilt by
`scripts/render_skeleton_diagrams.py`, which calls
`skeleton_catalog.build_catalog_region()` under the hood); re-run that script and read
that doc rather than re-deriving the list here.

Cover **every** file, including the 3 non-production MVP seeds (Lost Mitten,
Clocktower Cipher, Sunken Signal); they are cheap and exercise the MVP-tier code
path (relaxed floors, `production_eligible: false`), which is otherwise untested by
this effort.

## Authoring paths to exercise

Three test-driver paths (A, B/B', C below) reach the database from a skeleton for the
purposes of this proof pass. Two further codebase paths must be distinguished from them
and from each other: the **skeleton_fill story-request pipeline**, now the live
production route that selects from `skeletons/` (in scope, described after the table),
and the **concept-brief fresh-generation** path, which never reads `skeletons/` (out of
scope). Call both out explicitly so they don't get conflated with the drivers above.

| Path | Entry point | What it does | Needs |
| --- | --- | --- | --- |
| **A. cyo-author skill (LLM-authored)** | `.claude/skills/cyo-author` skill, invoked per skeleton | Uses the active model to write `<<FILL>>`-compliant prose, then validates and imports | Interactive session; one run per skeleton |
| **B. Direct import (scripted)** | `import_filled_story()` (`src/cyo_adventure/generation/import_story.py`), called from a batch harness against pre-filled JSON | Same validate-then-persist-then-moderate flow as the CLI, but scriptable across all 21 skeletons in one pass | A filled JSON per skeleton (can reuse Path A's output), a `family_id` UUID already present in the dev DB |
| **B'. CLI import** | `uv run python -m cyo_adventure.generation.import_cli <path> --family <uuid>` (`main()` in `src/cyo_adventure/generation/import_cli.py`) | Same as B, one file at a time from the shell | Same as B; useful for spot-checking a single skeleton without a script |
| **C. Moderation-bypassed smoke pass** | Path A/B with `OPENAI_API_KEY=""` and `PERSPECTIVE_API_KEY=""` | Same validate + persist, but classifiers short-circuit (`run_classifiers()` in `src/cyo_adventure/moderation/classifiers.py` returns `[]` when both keys are falsy), isolating "does the fill + import mechanics work" from "does moderation behave" | Removes only classifier (Stage 0) traffic; a run is fully external-free only if `generation_provider`/`review_provider` also stay `mock` (their defaults), since Path A authors with a live model. Fastest first pass |

**Now-live production path (in scope), do not confuse with the drivers above:** since
WS-C PR2 (#175), skeleton selection is implemented, so a story request can now author
directly from the corpus. `generation/skeleton_match.py` (`candidates_for_cell()`,
`select_skeleton_for_cell()`, `resolve_skeleton_path()`) is wired into
`story_requests/authoring_plan.py` (`_resolve_skeleton_fill()`), which picks a skeleton
from `skeletons/` for a `skeleton_fill` authoring plan; the worker's
`_run_skeleton_fill()` (`generation/worker.py`) then loads that file via
`resolve_skeleton_path()` and fills it. This is the real production route from the
corpus to the database and shares the same validate → persist → moderate tail as Paths
A/B/B', so it is the strongest end-to-end exercise of this plan's premise. Cover it in
addition to the driver paths.

**Explicitly out of scope, do not confuse with the above:** the concept-brief API route
(`POST /api/v1/concepts/{concept_id}/generate`, `enqueue_concept_generation()` in
`src/cyo_adventure/api/generation.py`) and the fresh-generation branch of its worker
(`run_generation_job()` in `generation/worker.py`, which calls `generate_story()` in
`generation/orchestrator.py`) generate **fresh** structure from an LLM on every call and
never read `skeletons/`. The worker routes on whether the authoring plan carries a
`skeleton_slug`: a `skeleton_fill` plan goes to `_run_skeleton_fill()` (the production
path above); a fresh-generation plan goes to `generate_story()`. Running the
fresh-generation path tells you nothing about the skeleton corpus.

**Known trap, verify it is not silently substituted:** the canned "The Forest Path"
story that has been observed to replace all authored content regardless of input skeleton
(observed during earlier local story-creation testing) comes from the generation
`MockProvider` (`src/cyo_adventure/generation/provider.py`), which is selected whenever
`generation_provider` is left at its default of `"mock"` (`src/cyo_adventure/core/config.py`).
It is **not** produced by `seed_dev_data.py`, which only inserts real fixture blobs from
`tests/fixtures/storybook/valid/`. Set a real `generation_provider` (e.g. `openrouter`)
before any generation path (Path A, and the live skeleton_fill pipeline) so the model, not
the mock, writes the prose. Before trusting any result, confirm the persisted
`StorybookVersion.blob` actually contains prose distinct per skeleton, not a repeated
canned body.

## Per-skeleton success criteria

For each `(skeleton, path)` pair:

- [ ] `run_gate()` on the **filled** story returns `blocked=False` (structure alone
      already passes pre-fill; this reconfirms post-fill, since prose length can
      violate the per-node word wall).
- [ ] `persist_storybook()` creates a `Storybook` row and a `StorybookVersion` row;
      the blob's `id` matches the DB row id (the existing `#CRITICAL` invariant in
      `persist_storybook()`, `persistence.py`).
- [ ] The story leaves `draft` for `in_review` (clean or repaired) via
      `run_moderation_pipeline()`, or `needs_revision` if the content is
      intentionally provocative for that band (record which, don't just note pass/fail).
- [ ] The stored prose is distinct per skeleton (guards against the mocked-stack trap
      above).
- [ ] Word count per node stays within the cell's per-node max (spot-check a sample,
      not every node, unless a gate failure points at a specific node).

## Execution notes (from prior local-run experience)

- Run with `uv run --env-file .env` so live provider keys (openrouter generation,
  OpenAI classifier) are loaded.
- DB runs on port 5442 locally (5432 is taken by another project).
- `import_cli`/`import_filled_story` need a `family_id` that already exists in the dev
  DB (FK constraint); reuse the dev guardian/family seeded by `seed_dev_data.py`
  rather than inventing a UUID.
- Approval/read-gate state (`approved_by` + assignment) is separate from moderation
  status; landing in `in_review` does not make a story readable by a child profile.
  That is out of scope for this plan (it is a review/assignment workflow question,
  not an authoring-path question) but don't mistake "persisted and in_review" for
  "playable."

## Results tracking

One row per `(skeleton, path)`. Populate as the pass runs; this table starts empty.

| Band | Skeleton | Path A (skill) | Path B/B' (direct/CLI import) | Path C (moderation-bypassed) | Notes |
| --- | --- | --- | --- | --- | --- |
| 3-5 | the-lost-mitten (MVP) | | | | |
| 3-5 | the-clover-and-the-butterfly | | | | |
| 3-5 | the-teddy-bears-picnic | | | | |
| 5-8 | the-backyard-treasure-map | | | | |
| 5-8 | the-lantern-festival | | | | |
| 8-11 | the-cave-of-echoes | | | | |
| 8-11 | the-clockwork-menagerie | | | | |
| 8-11 | the-sky-ship-stowaway | | | | |
| 10-13 | the-clocktower-cipher (MVP) | | | | |
| 10-13 | the-hollow-lighthouse | | | | |
| 10-13 | the-mapmakers-island | | | | |
| 10-13 | the-midnight-museum | | | | |
| 13-16 | the-signal-in-the-static | | | | |
| 13-16 | the-sunspire-ascent | | | | |
| 13-16 | the-thornwood-trial | | | | |
| 13-16 | the-vanishing-orchard | | | | |
| 16+ | the-ashfall-expedition | | | | |
| 16+ | the-drowned-court | | | | |
| 16+ | the-last-train-north | | | | |
| 16+ | the-salt-archive | | | | |
| 16+ | the-sunken-signal (MVP) | | | | |

## Open decisions

1. **Coverage depth.** Run all three paths (A, B/B', C) against every one of the 21
   skeletons (63 attempts), or run Path C (fastest, cheapest) across the full corpus
   first and reserve Path A (slowest, uses real model + classifier spend) for a
   sample plus any skeleton that fails Path C? Recommend the latter: full-corpus
   smoke via C, then A on a representative sample (one per band) plus anything C
   flagged.
2. **Failure handling.** If a skeleton fails post-fill gate validation (e.g., an LLM
   overshoots a node's word budget), is that a skeleton bug (the FILL directive's
   `words=N` budget was set too tight against the cell max) or an authoring-prompt
   bug (the model doesn't respect `words=N`)? Decide the triage owner before running,
   so failures don't stall waiting on a decision made per-incident.
3. **Where results live.** This doc's results table, or a separate tracking issue per
   failure? Recommend: pass/fail summary in this doc's table, one GitHub issue per
   confirmed skeleton-content bug (not per transient moderation flake).
