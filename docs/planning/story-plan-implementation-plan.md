---
title: "Story Plan implementation plan"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Phased work breakdown for ADR-033: the per-book Story Plan, its structural checks, plan
  generation, typed directives, scene-by-scene fill, evaluation led by reads, and the pilot. Each work
  package states files, inputs, outputs, dependencies, acceptance criteria, its evidence gate, size,
  spend and whether it needs an owner decision, so one package can be handed to one agent."
tags:
  - planning
  - generation
  - evaluation
  - implementation
---

# Story Plan implementation plan

> **Status**: draft for owner approval, 2026-11-21; owner decisions D1 and D2 made 2026-11-21 (section 13), and D11 (plans approved by a validated
> reviewer, amending ADR-033 Decision 3) made 2026-11-21 after ratification.
> **Decision record**:
> [ADR-033](./adr/adr-033-story-plan-meaning-layer.md) (Accepted 2026-11-21). **Source**: [architecture review,
> 2026-11-20](./architecture-review-2026-11-20.md) with its short-request addendum.
>
> **What is and is not established.** The review ran no generation. Every effort, cost and latency figure below is an
> estimate; the package that first measures each one is named beside it. Phase 1 is a no-spend retrospective test,
> placed first so that the idea can fail cheaply.
>
> **Serves** (capability register): K3 (choices are consequential), K11 and G4 (story requests), K19 (request
> interpretation), G5 and G6 (review and edit), A6 (approval gate, unchanged), A10 (admin-initiated generation), A11
> (structural quality tools), S3 and S4 (story representation and pre-publication validation).

## 1. How to use this document

- One work package (WP) is sized for one agent session or a short series. Each lists the files it may touch. A package
  that needs a file outside its list stops and reports.
- A package may start only when its dependencies are done **and** the evidence gate of the previous phase has passed.
  Gates are in section 9.
- Sizes: **S** under a day, **M** a few days, **L** a week or more, in agent working time with review. Uncertainty is
  stated in section 11.
- "Spend" is provider spend for paid generation. Work done inside a Claude Code session (the `skill` mechanism) is
  counted as no provider spend.
- Standing rules for every package: feature branch, signed Conventional Commits, RAD tags in `src/`, no em-dash, the
  lessons-log and register rules in `CLAUDE.md`. Any backend route or model change regenerates the frontend client in
  the same change.
- **No requester-facing model text.** No package may show a generated pitch, plan or passage to a child before final
  approval (ADR-015, owner ruling 2026-11-21).

## 2. Phase table

| WP | Title | Size | Spend | Owner decision |
| --- | --- | --- | --- | --- |
| 0.1 | Freeze list as concrete actions | S | none | D2: confirm the list |
| 0.2 | Short-request baseline design and code tag | S | none | no |
| 0.3 | Hand-written plans for the family-test books | M | none | D3: which books |
| 0.4 | Second-reader continuity pass and fixes | M | none | no |
| 0.5 | Family-test instrumentation and debrief | S | none | D3: enable reading trail |
| 1.1 | Story Plan schema v0 | M | none | D1: ratify ADR-033 |
| 1.2 | Structural checks SP-1 to SP-9 and CLI | M | none | no |
| 1.3 | Known-defect corpus | S | none | no |
| 1.4 | Blind plan extraction for the retrospective | M | none | no |
| 1.5 | Retrospective run and gate report | S | none | D5: gate verdict |
| 2.1 | Brief unpinning for 8-11 and up | S | none | no |
| 2.2 | Retained shapes and typed directive format | M | none | D4: which shells |
| 2.3 | Pitch and plan generation, persistence | L | 5 to 15 USD | no |
| 2.4 | Plan approval: validated reviewer, owner by exception | M | none | D11 made; D12 via WP-3.7 |
| 2.5 | Directive compiler and single scene template | L | 5 to 10 USD | D9: recap rule per band |
| 2.6 | Scene-by-scene fill with ledger context | L | 10 to 20 USD | no |
| 2.7 | Reading-level measure fix | S | none | no |
| 3.1 | Reader validation set and thresholds | S | none | D6: thresholds |
| 3.2 | Continuity reader stage | M | 5 to 10 USD | no |
| 3.3 | Request-fidelity measure | S | none | no |
| 3.4 | Reading-trail report extensions | S | none | no |
| 3.5 | Approver: three paths and one quality question | M | none | D8: wording |
| 3.6 | Demote regex detectors to smoke tests | S | none | no |
| 3.7 | Plan reviewer: validation, independence rule, exception sampling | M | 5 to 10 USD | D12: thresholds, sample rate |
| 4.1 | Short-request panel, baseline arms | M | 30 to 60 USD | D7: budget |
| 4.2 | Short-request panel, plan-first arm | M | 20 to 60 USD | D7 |
| 4.3 | Ten-book pilot | L | 10 to 30 USD | D7 |
| 4.4 | Decision report | S | none | D10: adopt, restrict or stop |

## 3. Phase 0: now, no spend

### WP-0.1 Freeze list as concrete actions

- **Goal.** Stop the work streams the review says to stop, without deleting anything, and leave a record.
- **Touches.** `docs/planning/unscheduled-work-register.md` (dispositions, by the orchestrator from Appendix B),
  `docs/planning/roadmap.md` (one note in the Content workstream), status banners at the top of
  `docs/planning/ws8-parameterize-at-promotion-runbook.md`, `docs/planning/story-structure-improvement-plan.md` and
  `docs/planning/structural-verification-2026-11-20.md` section 6. No code.
- **Actions.**
  1. Do not run: `scripts/flywheel_cycle.py`, `flywheel_scan.py`, `flywheel_candidates.py`, `mutate_skeleton.py`,
     `calibrate_mutation_floors.py`, `add_consequence.py`, `parameterize_promotion.py`, `prepare_promotion_pr.py`,
     `compare_vendors.py`, `compare_skeleton_authors.py`, `run_diversity_eval.py`, and any paid prompt A/B.
  2. Stays merged and unused: `src/cyo_adventure/mutation/`, `src/cyo_adventure/flywheel/` (confirm with `grep -rn
     "cyo_adventure.flywheel" src` that nothing on the request path imports it; the review's grep found no importer
     outside the package), `mutation/state_promotion.py`, the six promoted pilot shells.
  3. Stays merged and in use: the reader-agency prompt rules, merge notes, the declared-person fix, `--strict-agency`
     on promotion (it guards a path nobody is using), the edition importer, the reading-level loop.
  4. Do not use the six promoted shells for a reskinned request until one reskinned fill of each has been read
     (addendum A.5 item 6). Record this as a selection note; no code change, since on-demand generation is not in use
     for the family test.
  5. No new skeletons, no strict remediation of the 66 failing shells, no growth of
     `scripts/stateless_shell_grandfather.txt` work.
- **Acceptance.** The three banners exist and link to ADR-033; Appendix B rows are applied; `check_work_linkage.py`
  passes.
- **Gate.** None. **Depends on.** D2.
- **Status.** Delivered 2026-11-21 after D2 (approved by the owner in session, 2026-11-21) and D1 (ADR-033 ratified
  the same day). The freeze is a stop-using instruction, enforced by the status banners, the roadmap note and the
  register dispositions; no script was disabled or gated in code. Two corrections to the action text, from the code
  as it stands:
  - `scripts/run_diversity_eval.py --check` runs in the `diversity` job of `ci.yml` (and the local nox `diversity_eval` session), and `scripts/calibrate_mutation_floors.py --check` runs in `skeleton-promotion.yml` (path-triggered on `skeletons/**`). These are
    deterministic `--check` gates over committed data, not generation runs or paid work. They stay, so no passing CI
    job changes. "Do not run" applies to the scripts' operating modes (cycle, scan, candidates, mutate, calibrate
    without `--check`, evaluation rounds).
  - The `grep` in action 2 finds no importer of `cyo_adventure.flywheel` or `cyo_adventure.mutation` outside those
    packages, but `src/cyo_adventure/analysis/flywheel_input.py` refers to `flywheel.strategy` in docstrings only (no
    import), so the premise holds.
- **Selection note (action 4).** The six promoted pilot shells are not to be used for a reskinned request until one
  reskinned fill of each has been read (addendum A.5 item 6). This is a selection note only: on-demand generation is
  not in use for the family test, and no code gates it.

### WP-0.2 Short-request baseline design and code tag

- **Goal.** Make the pre-change behaviour reproducible so the baseline can be run at any later time.
- **Touches.** New `docs/planning/evidence/short-request-panel/README.md` and `panel.json` (design only); a git tag
  `baseline/pre-story-plan` on the current `main` merge of this branch.
- **Inputs.** `PREMISE_PANEL` in `scripts/measure_theme_coverage.py:53-70` (16 requests); the dragon line; three
  two-sentence guardian briefs to be written here.
- **Outputs.** `panel.json`: 20 requests, each with a hand-written element list of three to five items (for example:
  dragon; afraid; the dark; some change by the end), fixed before any generation. Bands 8-11 and 10-13, so 40 jobs per
  arm. Arms: (a) skeleton fill, (b) fresh generation, (c) plan-first. Measures and kill criterion as section 7.
- **Acceptance.** Element lists reviewed by the owner or a second agent; the tag exists; the README states the harness
  to reuse (`docs/planning/evidence/structural-verification-2026-11-20/run_fill.py` is the model).
- **Note.** The verification run already filled from an old worktree against a new one, so tagging is sufficient and
  the paid baseline (WP-4.1) need not run now.

### WP-0.3 Hand-written plans for the family-test books

- **Goal.** One plan per book going to the children, written by reading the book, in the draft shape of ADR-033
  Decision 1.
- **Touches.** New `out/<slug>.plan.json` for each of the seven family-test books fixed by D3 (2026-11-21): the four
  revised books `the-sky-ship-stowaway` (8-11), `the-hollow-lighthouse` (10-13), `the-midnight-museum` (10-13) and
  `the-signal-in-the-static` (13-16), and the three unrevised controls `the-cave-of-echoes` (8-11, the original
  edition; the partial revision on branch `wt/book-cave` stays parked), `the-mapmakers-island` (10-13) and
  `the-vanishing-orchard` (13-16). Nothing else. `the-sunken-signal` is not in the list.
- **Method.** Per book: cast with wants and voices; the truth; facts with ids; per node `establishes` and `requires`
  as the prose actually has them; threads from the declared variables; ending gifts. Record facts as written,
  including any that contradict each other: do not tidy the book while writing its plan.
- **Outputs.** The plan files, and a short note per book of how long it took and how many facts and threads it needed.
  **This is the first measurement of plan size and authoring time**, which sections 11 and WP-2.3 depend on.
- **Acceptance.** Every node and choice id in the book appears in its plan; JSON parses; a second agent can answer
  "what does the reader know on entering node X" from the plan alone for ten sampled nodes.
- **Depends on.** D3 (decided 2026-11-21). **Size.** M (the review's guess is two to four hours per book; untested;
  seven plans, not four).

### WP-0.4 Second-reader continuity pass and fixes

- **Goal.** Close AL-790 for the books the children will read, and create labelled defect data.
- **Touches.** The same `out/<slug>.filled.json` and `.plan.json` files for the seven D3 books; new
  `docs/planning/evidence/story-plan-retro/findings-<slug>.md`. Books are re-imported with
  `generation/import_catalog.py --only --edition`.
- **Method.** A reader that did not write the plan plays every `(node, state)` reachable configuration (the
  `StoryEngine` snippet in `.claude/skills/cyo-author/reference/story-agency-revision.md`) and lists each passage that
  asserts a fact the plan does not guarantee on entry, each contradiction with `truth`, and each payoff that leans on
  another. Fix the book; update the plan; keep the pre-fix finding with node id, state and quoted sentence.
- **Also.** The three `hollow-lighthouse` blockers AL-790 refers to are now written down in `docs/planning/evidence/structural-verification-2026-11-20/lighthouse-continuity-read.md` (B1 to B3,
  with should-fix S1 to S4 and minor M1 to M8), each with node, route, state and quoted sentence. WP-1.3 takes B1 to
  B3 from that file. They are unfixed in `out/the-hollow-lighthouse.filled.json` (unchanged since `15b14a1`) because book
  editing is paused (`UW-M20`); this pass applies the fixes once the owner lifts that pause, and keeps the file as the
  pre-fix record.
- **Controls (D3, 2026-11-21).** The three unrevised controls (`the-cave-of-echoes`, `the-mapmakers-island`,
  `the-vanishing-orchard`) get a plan (WP-0.3) and the same continuity read, so their defects are known and labelled.
  Only plain contradictions found in a control are fixed (a fact asserted that the book itself contradicts). Agency
  problems (dominated choices, choices that change nothing, endings reachable by one route) are recorded in the
  findings file and **never fixed**, so each control stays a valid unrevised comparison for the family test.
- **Edit pause (2026-11-21).** The owner lifted the book-editing pause (`UW-M20`) **for these seven books only**:
  WP-0.4 fixes may proceed on them. All other book editing stays paused.
- **Acceptance.** Zero open findings per book (for a control, zero open plain contradictions; recorded agency
  problems stay open by design); findings files committed; gate and `check_fill_integrity.py` pass on
  each revised book.
- **Gate (family test).** A book goes to the children only with a plan and a clean second read.

### WP-0.5 Family-test instrumentation and debrief

- **Goal.** Decide before the session what will be looked at.
- **Touches.** `docs/planning/r1-live-e2e-checklist.md` (family-session section); environment setting
  `READING_TRAIL_ENABLED` (owner action, D3).
- **Outputs.** A five-question spoken debrief; the list of signals to read from `scripts/report_reading_trail.py`
  (finish rate, stop nodes, choice split per decision, rewinds, endings reached, replays). Output stays on the owner's
  machine (ADR-030 Decision 6). With D3 the session compares **revised against control books, per band**, so the
  checklist also frames that comparison and how to read it honestly at four children (direction, not significance).
- **Acceptance.** Checklist updated; one dry run of the report against a local database.
- **Status (2026-11-21).** Checklist section written ("Family-test books: capture, debrief and reading the
  comparison" in the family-session section). Dry run done against a local Postgres 17 migrated with the real
  `supabase/migrations` chain and seeded with synthetic trails for two books: the report printed per-book started and
  finished counts, endings, stop nodes, per-decision picks and rewinds, and the per-profile split. Turning capture on
  in production is an **owner step** (see the checklist, step `B6`): apply migration
  `20261120120000_add_reading_trail` with the normal deploy, set `READING_TRAIL_ENABLED=true` on the production
  backend container, restart it. It has not been done.

## 4. Phase 1: Story Plan schema and structural checks, validated retrospectively

Nothing in Phase 2 is built until WP-1.5 passes.

### WP-1.1 Story Plan schema v0

- **Touches.** New package `src/cyo_adventure/storyplan/` (`__init__.py`, `models.py`, `schema_export.py`); new
  `schema/storyplan.schema.json`; `scripts/check_schema_parity.py` if it enumerates schemas; new
  `tests/unit/test_storyplan_models.py`. Read-only reference: `skeletons/10-13/the-clocktower-cipher.narrative.json`,
  the WP-0.3 plans.
- **Inputs.** ADR-033 Decision 1; the hand-written plans (the schema must accept them without loss, or the difference
  is recorded).
- **Outputs.** Pydantic v2 models with `extra="forbid"`; `plan_version`; shape id and hash binding; pure module, no
  I/O.
- **Acceptance.** All WP-0.3 plans validate; a plan with an unknown node id, an undeclared fact id or a thread naming
  an undeclared variable is rejected; `basedpyright` and `ruff` clean; coverage of the new package at or above 90
  percent.
- **Depends on.** WP-0.3, D1. **Size.** M.

#### WP-1.1 notes: schema v0 as built (2026-11-21)

Built in `src/cyo_adventure/storyplan/models.py`, exported to `schema/storyplan.schema.json`
(`uv run python -m cyo_adventure.storyplan.schema_export`). The module docstring is the full contract. The schema was
built in parallel with WP-0.3 and then reconciled with both sets of hand-written plans: the **family-test set**
(`the-hollow-lighthouse`, `the-sky-ship-stowaway`, `the-midnight-museum`, `the-signal-in-the-static`) is the canonical
shape and validates unchanged; the **control set** (`the-cave-of-echoes`, `the-vanishing-orchard`,
`the-mapmakers-island`) needs the mechanical migration below. The control set's additive ideas (choice `establishes`,
`implicit_plant`, ending `valence`/`kind`, free-form notes) were adopted into the canonical shape.

What a plan writer must follow:

- **Top level**: `plan_version` (`"0.1"`; `"0.0"` is still read), optional `book`, `request`, `pitch`, `cast`,
  `truth`, `facts`, `nodes`, `choices`, `threads`, `endings`, `provenance`. Unknown keys are rejected everywhere.
- **Sections keyed by id are JSON objects**, not arrays. Node and choice keys are the book's ids verbatim; fact,
  thread and cast ids match `^[a-z][a-z0-9_]*$`.
- **`book`** (optional): `slug`, `storybook_id`, `storybook_version`, `title`. SP-0 checks id and version.
- **`request`**: `band` required (must equal the book's `metadata.age_band`); `text`, `length`, `style`, `tone`,
  `note` optional.
- **`pitch`**: `hero`, `want`, `obstacle`, `stake`, `ending_kind`, all required.
- **`cast`**: per character `name`, `role`, `want`, `voice`, `knows` (fact ids).
- **`truth`**: `statement` (the one canonical answer), `facts` (one or more fact ids), optional `question`. Truth facts
  may not contradict each other.
- **`facts`**: per id `{"text", "contradicts"?, "implicit_plant"?}`. `contradicts` may be written on one side or both;
  it is read both ways. A negative assertion ("she has no key") is a positive fact that contradicts its opposite. A
  partial reveal is its own fact. Facts only accumulate; a change of state is a new fact. `implicit_plant` is a note
  for a setup with no variable; no rule reads it.
- **`nodes`**: per node `function` (free text; the family set's vocabulary is recommended), `event`, `requires`,
  `establishes`. A node may both require and establish a fact, so one merge defect does not cascade.
- **`choices`**: `intent`, `cost` required; optional `requires` (checked where the choice is visible, against what is
  known on entry plus the node's `establishes`; a plan may instead fold label presuppositions into the node's
  `requires`), `establishes` (facts taking the choice establishes on entry to its target), `plants` (a thread id or a
  list).
- **`threads`**: `variable`, `plant` (one fact id), `planting_choices` (every choice whose effects set the variable off
  its initial value), `payoff_sites`: `[{"node", "choice", "shows"}]`, where `node` is reached with and without the
  plant and `choice` is the choice there (gated true or false) through which the payoff shows. Every book variable
  needs exactly one thread. A choice's `plants` must name `t` exactly when `t.planting_choices` lists it.
- **`endings`**: keyed by ending node id, `{"gift", "valence"?, "kind"?}`; required for every negative ending;
  `valence` and `kind`, when given, must match the book.
- **`provenance`**: `producer` required; binding by `shape` (`{"id", "hash"}`, hash from
  `scripts/check_story_plan.py <book> --shape-hash`, graph only) and/or `book_sha256` (hex SHA-256 of the book file's
  bytes; any edit makes the plan stale, which suits a plan written by reading the prose). Optional `model`, `method`,
  `book_file`, `authored`, `authoring_minutes`, `checks` (`{ok, errors, warnings}` or null), `approver`, `notes`
  (list of strings).
- **SP-9 applies to every plan string** except `request.text`, `request.note`, `book`, `provenance` and
  `implicit_plant`: one line, no `{`, `}`, `<<`, `>>`, em dash or fence marker, and no
  band-mandatory denylist term. Length is capped per field (amended 2026-11-21, slot versus record prose): 120
  characters for slot-like strings (pitch, cast, choice intent and cost, endings, payoff `shows`, tone), 240 for
  `facts.*.text` and node `event`, 600 for `truth.statement`. As first measured, on the seven hand-written plans this is the largest source of findings: 69 strings
  over 120 characters (39 in the family set, 30 in the control set) and five uses of "wound" for clockwork, which the
  `graphic` bundle matches at 10-13.

Migration of the control set, nine mechanical edits per file:
`truth.answer` to `truth.statement`; `request.source` to `request.note`; `provenance.book{id, version, path, sha256}`
to a top-level `book{slug, storybook_id, storybook_version, title}` plus `provenance.book_file` and
`provenance.book_sha256`; drop `provenance.shape` (its hash basis is not `shape_hash`, and the file hash already binds
the plan) or replace it with the `--shape-hash` value; drop `provenance.declared_variables` (SP-1 reads the book);
move `provenance.threads_note` and `provenance.continuity_notes` into `provenance.notes`; rename
`provenance.check_results` to `provenance.checks`; optionally set `plan_version` to `"0.1"`. After that conversion all
three files validate and check.

### WP-1.2 Structural checks and CLI

- **Touches.** New `src/cyo_adventure/storyplan/checks.py`; new `scripts/check_story_plan.py`; new
  `tests/unit/test_storyplan_checks.py`. Reuses `validator/walk.py` (configuration walk) and the fixpoint in
  `scripts/check_narrative_contract.py` (moved, with that script importing it so
  `tests/unit/test_check_narrative_contract.py` still passes).
- **Outputs.** SP-1 to SP-9 as in ADR-033, each returning findings in the `validator/report.py` shape, with a witness
  document per rule in the style of `validator/blind_spots.py` (a plan built to trip exactly that rule).
- **Acceptance.** One failing witness and one passing fixture per rule; the checker is deterministic (two runs,
  identical output); runs in under ten seconds on the largest WP-0.3 plan.
- **Depends on.** WP-1.1. **Size.** M.

#### WP-1.2 notes: checks as built (2026-11-21)

`src/cyo_adventure/storyplan/checks.py`; CLI `scripts/check_story_plan.py`. Rule definitions are in the module
docstring. Departures from ADR-033's table, all additive:

- **SP-0** (binding) implements the ADR's "a stale plan fails its checks": no binding, a mismatched `shape` hash or
  `book_sha256`, a `book` block naming another book, a band mismatch, or a capped configuration walk.
- **SP-2 is state-aware** and covers choices. The NC-1 fixpoint moved into the package (`guaranteed_on_entry`, with
  `scripts/check_narrative_contract.py` importing it; its output is byte-identical on both committed contracts) and
  runs over the configuration graph, with choice plants and choice `establishes` as edge facts. A node reached only by
  planted readers has the plant guaranteed. A choice's `requires` is checked only in states where it is visible.
- **SP-3 is route-aware with a documented split.** A contradicting pair one reading can meet (found by a search over
  `(configuration, holds first, holds second)`, plants included) is an ERROR: this is what catches Lighthouse B2. A
  pair only on routes no single reading crosses is an ERROR if either side is a `truth` fact (the two-backstory class,
  AL-773) and a WARNING otherwise (the Museum cipher variants). A writer who wants a detail held fixed across routes
  puts one side in `truth`.
- **SP-4** also counts a non-planting choice whose `establishes` names the plant.
- **SP-5** also requires each payoff `choice` to be offered in at least one reachable state of its site.
- **SP-6** is a plant-blind re-run of the fixpoint (no choice plants anything; other threads' payoff passages, the
  targets of their payoff choices, establish nothing), applied to the payoff choice's `requires` and the passage's
  `requires` in states entered through that choice.
- **SP-A** (`--assertions`) compares a per-node assertion map (a JSON object of node id to asserted fact ids, the
  WP-1.4 `assertions/*.json`) with the computed `must_not_assert` (`--must-not-assert`). This is the comparison WP-1.5
  runs.
- `--verify-witnesses` runs one witness per rule plus the clean example; each witness must trip its rule and no other.
  The Hollow Lighthouse (162 nodes, 1,214 configurations) checks in about 1.5 s.

**G1 revision (2026-11-21).** The single revision D5 permits after the failed G1 run, before one re-run on the same
frozen answer key with the criterion unchanged. Each change is justified by the rule's purpose in ADR-033, keeps
catching its defect class, and names no book, node, fact or answer-key entry:

- **SP-4, AL-817.** The facts checked are the declared `plant` plus every other fact the planting edge makes known (the
  planting choice's `establishes`, and its target's `establishes` when only planted readers arrive there, less what the
  reader already had guaranteed) that a payoff of the thread relies on (a payoff choice's `requires` or its passage's).
  A public plant is therefore caught whichever half of a two-part plant the plan names as `plant`. New witness: the
  plan names the private half and the shared path shows the public half.
- **SP-4, AL-818.** A checked fact is reported only at a configuration from which a payoff site of the thread is still
  reachable without a planting choice, so an ending that reveals the plant is never reported.
- **SP-8, AL-819.** A decision whose options share one cost is an ERROR only when that cost is "none" (also spelled
  "nothing" or "no cost", now one value): no option gives anything up, so no trade-off separates them. A shared real
  cost, each option giving up the others, is a WARNING. The convention is written into the re-extraction prompt
  (`evidence/story-plan-retro/plans/EXTRACTION-PROMPT-v2.md`).
- **SP-9, AL-811.** SP-9 alone masks the bare word "wound" before the denylist when the string names a winding context
  (clockwork, clock, spring, key, crank, wind and listed forms, or "wound up", "wound tight") and the word before it is
  not a determiner, possessive, injury adjective, "to" or a modal. `validator/slots.py` is unchanged; "wounded", the
  injury sense and every other term still fail. New witness: "a wound from the clock key".
- **SP-1, AL-821.** Only a node or choice coverage gap stops SP-2 to SP-8. A thread with an SP-1 error is excluded from
  SP-4 to SP-6 (its plants still feed the must-analysis as declared) and everything else runs and is reported.
- **SP-3, AL-822.** No change: a test pins that a node asserting a negation, reached on a route whose choice planted
  the opposite, is an SP-3 ERROR. The fix is in extraction: the v2 prompt asks for negations about the hero's
  possessions, knowledge or state to be recorded at the passage that asserts them.

First run on the family-test plans (no tuning to the known-defect list, which this package did not read): the
Lighthouse plan yields SP-2 or SP-3 findings at the nodes of B1 (`e_win_keeper_word`, `ferris_warned_bog`), B2
(`cm_light_relight`, `has_key` against `mira_lacks_lamp_key`), B3 (`e_win_harbor`, `grey_boat` and the Varley name),
S1, S3, S4, M3 and M4 of `lighthouse-continuity-read.md`. That is indicative only: the plan was written by an agent
that had read the continuity notes, so it is not the blind test WP-1.4 and WP-1.5 define.

### WP-1.3 Known-defect corpus

- **Touches.** New `docs/planning/evidence/story-plan-retro/known-defects.json` and `README.md`.
- **Contents**, each with source, book file or git revision, node id, state, quoted sentence and defect class:
  1. The three `hollow-lighthouse` continuity blockers B1 to B3 (AL-790), from `docs/planning/evidence/structural-verification-2026-11-20/lighthouse-continuity-read.md`; S1 to S4 as
     should-fix entries. The file is already committed, so this item does not wait on WP-0.4.
  2. The two-backstory contradiction in the original `hollow-lighthouse` fill (AL-773); the pre-revision book is `git
     show 15b14a1^:out/the-hollow-lighthouse.filled.json`.
  3. The three leaks in the 2026-11-20 Run B fills: `B-lkl-new-2` node `fn_ovens`; `B-os-new-1` ending `e05_0`;
     `B-lkl-new-2` `cq_payoff_did_start_beacon_steps` (structural-verification section 4.2).
  4. The `did_find_who_wrote` plant on `the-orchard-signal`: one unearned and three thin payoffs across two fills.
  5. Any further findings from WP-0.4 on the other three books.
- **Acceptance.** Every entry resolvable to a file and node; the list is frozen (committed) before WP-1.4 starts.
- **Size.** S.

### WP-1.4 Blind plan extraction for the retrospective

- **Goal.** Produce plans for the defective artifacts without knowledge of the defect list, so the test is not
  circular.
- **Touches.** New `docs/planning/evidence/story-plan-retro/plans/*.plan.json` and `assertions/*.json`.
- **Method.** An agent that has **not** read `known-defects.json`, the AL rows above or the verification report
  extracts, for each of: the pre-fix revised books (the revisions before WP-0.4's fixes), the original
  `hollow-lighthouse` fill, and the four Run B fills
  (`docs/planning/evidence/structural-verification-2026-11-20/runs/B-*/filled.json`): (i) a plan from the shape and
  the book as a whole; (ii) per node, the list of plan facts that node's prose asserts. Step (ii) is the manual form
  of the continuity reader.
- **Acceptance.** Plans validate under WP-1.1; assertion files cover every node; the extracting agent's prompt is
  committed so the blindness claim can be audited.
- **Depends on.** WP-1.1, WP-1.3 frozen. **Size.** M. **Measures.** Extraction time per book, and how often two
  extractions of one book agree (run two for one book).

### WP-1.5 Retrospective run and gate report

- **Touches.** New `docs/planning/evidence/story-plan-retro/report.md`.
- **Method.** Run SP-1 to SP-9 on each plan; compare each node's asserted facts with its computed `must_not_assert`;
  match findings to `known-defects.json`.
- **Pass criterion (pre-registered here).**
  - Exact classes, must be 100 percent: the public plant (SP-4), the cross-payoff reference (SP-6), the two
    backstories (SP-3).
  - Assertion classes: all three Run B leaks found; at least two of the three Lighthouse blockers (B1 to B3 in
    `docs/planning/evidence/structural-verification-2026-11-20/lighthouse-continuity-read.md`) found, with a written reason for any miss.
  - False alarms: on the four revised books after WP-0.4, no more than one ERROR finding per book that a human judges
    wrong.
- **If it fails.** One revision of the schema or checks, time-boxed to size M, then one re-run on the same frozen
  corpus. If it fails again: stop. ADR-033 is withdrawn or narrowed; Phase 2 does not start; the fallback is the
  WP-0.4 second read as the standing continuity control for catalog books, plus the beat and label lint (`UW-C496`,
  `UW-C497`) on the shells in use. The report says so plainly.
- **Owner decision.** D5: accept the gate verdict. **Size.** S.

### WP-1.6 Fresh-corpus confirmation (added 2026-11-21, D5 condition 2)

- **Why.** G1 passed on its one re-run after a revision designed by an agent that had read the answer key. This package
  measures the revised checks and the plan-writing conventions on books nobody has used to design them.
- **Corpus.** Three catalog books (one per family band) that have not been read, planned or used anywhere in WP-0.3 to
  WP-1.5 or the plan-review pilot. Chosen by the orchestrator from the catalog by a seeded draw, recorded before any read.
- **Method, in this order.** (a) A WP-0.4-style second read of each book, findings frozen and committed first. (b) Blind
  plan extraction under `EXTRACTION-PROMPT-v2.md` by fresh agents that cannot see (a). (c) The checker run on (b),
  scored against (a) with the WP-1.5 "found" definition.
- **Pass criterion (pre-registered here).** Of the second read's blockers and should-fix items in the classes the fact
  model covers (unestablished fact on a route, state contradiction, two backstories, public plant, cross-payoff
  reference), at least half found across the three books, every exact-class item found; and no more than one ERROR per
  book that the owner judges wrong. Classes the fact model does not cover (timelines, location, physical state,
  repeated reveals) are reported, not scored.
- **If it passes.** The WP-0.4 second read may be retired as the standing control for catalog books (owner decision).
  **If it fails.** The second read stays; the report says which classes failed. Phase 2 is not blocked either way.
- **Depends on.** D5 (accepted). **Size.** M. **Spend.** none beyond agent time.

## 5. Phase 2: plan generation, directives, fill

### WP-2.1 Brief unpinning for 8-11 and up

- **Touches.** `src/cyo_adventure/story_requests/brief.py` (`:324`, `:328`), `src/cyo_adventure/generation/concept.py`
  if a field becomes optional, `src/cyo_adventure/generation/prompts.py` (`_budget_block`, `:366-422`),
  `tests/unit/test_story_requests.py`, `tests/unit/test_prompts.py`.
- **Change.** For bands 8-11 and up the brief no longer fixes `tier=1` or the pattern; the shape (skeleton path) or
  the plan (fresh path) supplies them. 3-5 and 5-8 unchanged.
- **Acceptance.** Existing skeleton-fill jobs produce byte-identical prompts (the brief's tier was not what decided a
  skeleton's tier); a fresh-generation brief at 8-11 may declare variables without tripping L1-6; no API schema change
  (verify with the `contract` CI job).
- **Independent of Phase 1.** May run any time after D1. **Size.** S.

### WP-2.2 Retained shapes and typed directive format

- **Touches.** `src/cyo_adventure/generation/fidelity.py` (`parse_fill_directive`),
  `src/cyo_adventure/generation/skeleton.py`, `src/cyo_adventure/storybook/slotted_surfaces.py` (`FILL_DIRECTIVE_RE`),
  `scripts/check_skeleton.py`, the retained files under `skeletons/8-11`, `skeletons/10-13`, `skeletons/13-16`, tests
  for each.
- **Change.** A version-2 directive, `<<FILL v=2 role=... words=... function=...>>`, with no `beats`. Version-1
  directives keep working unchanged for every shell not converted. `check_skeleton.py` rejects a v2 directive that
  carries free text. Each retained shell gets a shape id and content hash.
- **Inputs.** D4: the retained set, proposed as eight to twelve shells across the three family bands with at least two
  shapes per offered cell (addendum A.5 item 2). The six promoted pilots are candidates only after their native
  literals are removed.
- **Acceptance.** Converted shells pass the gate in skeleton posture and `--strict-agency`; unconverted shells are
  byte-identical; no shell loses production eligibility in this package.
- **Depends on.** WP-1.5 passed, D4. **Size.** M.

### WP-2.3 Pitch and plan generation, persistence

- **Touches.** New `src/cyo_adventure/storyplan/generate.py`; new templates
  `src/cyo_adventure/generation/templates/pitch.md`, `plan.md`, `plan_repair.md`;
  `src/cyo_adventure/generation/prompts.py` (builders); `src/cyo_adventure/generation/worker.py` (new branch beside
  `_run_skeleton_fill`); `src/cyo_adventure/db/models.py` (`StorybookVersion.story_plan`, `GenerationJob` report
  keys); a new file under `supabase/migrations/`; `src/cyo_adventure/api/schemas.py` (`AuthoringMethod` gains
  `plan_fill`); regenerated `frontend/src/client/`; tests.
- **Behaviour.** Request to two or three pitches (five required fields, each string floored by `validator/slots.py`
  and screened by the Stage 0 classifiers); first passing pitch is used for on-demand, owner-chosen for catalog; pitch
  plus shape to plan; SP checks; bounded repair with the findings as feedback; persist the plan and its check results.
  Request text is fenced as untrusted in every prompt. The plan is never serialised to a kid-surface route (add a test
  on `api/library.py` and `api/reading.py` response models).
- **Acceptance.** With a mock provider: a valid plan round-trips; an invalid plan is repaired or the job ends
  `needs_review` with the SP findings; PII in a request still hard-blocks. Paid smoke: five requests from the panel at
  8-11 each yield a plan that passes SP-1 to SP-9 within the repair budget. **This smoke is the first measurement of
  plan-generation yield, tokens and latency.**
- **Depends on.** WP-1.5, WP-2.2. **Size.** L. **Spend.** 5 to 15 USD.

### WP-2.4 Plan approval

- **Goal.** Approve plans, on both paths, by one rule: SP-0 to SP-9 pass, screening is clean, and a **validated** plan
  reviewer (WP-3.7), a different model from the plan's writer, passes the plan. The owner reads by exception
  (ADR-033 Decision 3 as amended 2026-11-21, owner decision D11).
- **Touches.** `src/cyo_adventure/story_requests/authoring_plan.py` (policy default with admin override in place of a
  per-request click), `src/cyo_adventure/generation/worker.py` (call the reviewer after clean checks; route to
  `needs_review` on anything but a clean `pass`, on a sampled pass, and while the reviewer is suspended or
  unvalidated), `src/cyo_adventure/storyplan/models.py` (additive minor: `provenance.approver` as a record of reviewer
  model, verdict, sample reason and, where the owner decided, the owner), `scripts/check_story_plan.py`
  (`--require-approval`), `src/cyo_adventure/events/` (event types for pass, reject, unsure, sampled and owner
  decision), `docs/operations/authoring-guide.md`. No frontend in version 1: exceptions reuse the existing
  `needs_review` admin queue.
- **Behaviour.**
  - On-demand: after the checks pass and screening is clean, the worker calls the reviewer through the WP-3.7 module.
    A clean `pass` that is not drawn for the sample proceeds to fill. A `reject`, an `unsure`, a reviewer error, a
    malformed answer, a provider outage, a writer-equals-reviewer pairing, an unvalidated or suspended reviewer, or a
    sampled pass routes the job to `needs_review`; the job does not reach fill until the owner clears it. The reviewer
    fails closed.
  - Catalog: the reviewer runs offline (`scripts/review_story_plan.py`, WP-3.7) and writes its verdict into
    `provenance.approver`. `scripts/check_story_plan.py --require-approval` runs in pre-commit and CI on
    `out/*.plan.json` and fails when a plan has no verdict, when writer and reviewer match, or when the verdict is
    `reject`, `unsure` or sampled and no owner decision is recorded. The pull request is no longer where a plan is
    approved; it is where the owner decides an exception.
  - The sample draw is a seeded function of the plan's content hash and the configured rate (proposed 1 in 10, D12), so
    it is auditable and cannot be re-rolled.
  - Nothing is shown to the requester.
- **Acceptance.** With a mock reviewer: a clean pass proceeds; each of the failure routes above sends the job to
  `needs_review` and never to fill; a writer-equals-reviewer pairing is refused; the sample draw is deterministic and
  hits the configured rate within a binomial tolerance over 1,000 synthetic hashes; the audit event records which
  checks passed, the plan hash, the reviewer model and its verdict; final approve-and-publish is unchanged
  (`publishing/` untouched, asserted by its existing tests).
- **Depends on.** WP-2.3 **and WP-3.7 (G3b)**. It does not merge with the reviewer enabled before the reviewer's
  validation has passed; until then the worker sends every plan to the owner.
- **Size.** M.

### WP-2.5 Directive compiler and single scene template

- **Touches.** New `src/cyo_adventure/storyplan/compiler.py`; new template `scene.md`;
  `src/cyo_adventure/generation/prompts.py`; `src/cyo_adventure/generation/merge_notes.py` (superseded for v2 shells,
  kept for v1); `src/cyo_adventure/moderation/fidelity_review.py` (target becomes `event` plus `must_not_assert` for
  v2); tests.
- **Behaviour.** Pure function: `(shape, plan, scene node ids, band rules) -> instruction`. The instruction states,
  for each node in the scene, its function and event, the facts guaranteed on entry, the facts it must not assert, the
  voices present, and for choices the intent, cost and required label person. Craft rules are rendered from one
  in-module table (the seed of the rule registry), not copied from the four fill templates.
- **Acceptance.** Deterministic output; for every merge node the instruction lists entry-guaranteed facts and contains
  no route narration; snapshot tests on two retained shapes; the v1 templates are untouched.
- **Owner decision.** D9: the per-band recap rule (AL-767), since the compiler must render one answer.
- **Depends on.** WP-2.2, WP-2.3. **Size.** L. **Spend.** 5 to 10 USD of smoke fills.

### WP-2.6 Scene-by-scene fill with ledger context

- **Touches.** `src/cyo_adventure/generation/orchestrator.py` (new `fill_from_plan` beside `fill_skeleton`),
  `src/cyo_adventure/generation/chunking.py` (scene partition; reuse `merge_fill_batch`'s whitelist merge),
  `src/cyo_adventure/generation/worker.py`, `src/cyo_adventure/generation/usage.py` and `cost.py` (per-scene
  accounting), `src/cyo_adventure/generation/reading_level_loop.py` (called per book as now), tests.
- **Behaviour.** A scene is a decision node with its single-choice arrivals. Scenes whose entry facts are fixed by the
  plan are filled concurrently, bounded by a setting; a failed scene is retried alone; labels come from the plan's
  intents. The model that served each scene is recorded (closes `UW-C500` for this path).
- **Acceptance.** Whitelist merge still cannot change ids, targets, conditions or effects; a book is never persisted
  with an unfilled scene (PL-27); on five paid smoke books: words delivered within 10 percent of commissioned per
  scene, and **input tokens, cost and wall-clock recorded against the one-shot baseline of the same shells**. This
  replaces the review's untested "two to four times input" estimate with a number.
- **Depends on.** WP-2.5. **Size.** L. **Spend.** 10 to 20 USD.

### WP-2.7 Reading-level measure fix

- **Touches.** `src/cyo_adventure/validator/reading_level.py`, `src/cyo_adventure/utils/sentences.py`, tests.
- **Change.** Score narration with speech handled as joined sentences and with the abbreviation guard
  `validator/naming.py` already has (AL-771, AL-785). RL-13 stays advisory; the loop stays.
- **Acceptance.** The first-draft `hollow-lighthouse` dialogue case no longer puts dialogue-heavy nodes under the band
  floor; no change in score for speech-free nodes across `out/`.
- **Independent.** **Size.** S.

## 6. Phase 3: evaluation

### WP-3.1 Reader validation set and thresholds

- **Touches.** New `docs/planning/evidence/continuity-reader/validation-set.json` and `README.md`.
- **Contents.** The WP-1.3 corpus; the 147 hand-read merge openings and 22 plant-payoff judgments from the 2026-11-20
  evidence; the post-fix revised books as negatives. Split once into a tuning half and a held-out half, by book, and
  commit the split.
- **Thresholds (proposed, D6).** On the held-out half: recall at least 0.8 on known defects; no more than one false
  flag per 50 nodes on the clean books; agreement between two runs at least 0.9. Fixed before WP-3.2 writes a prompt.
- **Shared with WP-3.7.** The split by book is made once and used by both the continuity reader and the plan reviewer,
  so neither is tuned on the other's held-out half. WP-3.1 also fixes the validation-set format (an `items` list with
  `kind`, `expected_verdict`, `defect_class`, `severity` and `source`) that WP-3.7 adds plan-level items to.
- **Size.** S.

### WP-3.2 Continuity reader stage

- **Touches.** New `src/cyo_adventure/moderation/continuity_reader.py`; `src/cyo_adventure/moderation/pipeline.py`;
  `src/cyo_adventure/moderation/report.py` (a `Source` member); `src/cyo_adventure/validator/paths.py` (path sampling,
  reuse); `src/cyo_adventure/api/review_surface.py`; tests.
- **Behaviour.** For sampled `(node, state)` paths, ask the review provider, per node, which listed facts the passage
  asserts; compare with `must_not_assert` deterministically. Advisory (`Verdict.ADVISORY`), fail-open, never quoting
  story text in messages. Runs only for books that have a plan.
- **Acceptance.** Meets the D6 thresholds on the held-out half. If it does not after one prompt revision on the tuning
  half, it ships as an offline script only and the approver relies on WP-3.5.
- **Depends on.** WP-1.5, WP-3.1. **Size.** M. **Spend.** 5 to 10 USD.

### WP-3.3 Request-fidelity measure

- **Touches.** New `scripts/measure_request_fidelity.py`; `docs/planning/evidence/short-request-panel/README.md`.
- **Behaviour.** Given a book, its request and the fixed element list, emit a rating sheet for a blind adult reader:
  one sampled path, each element present or absent, and "is this the story that was asked for", 1 to 5. The script
  assembles and tallies; a person rates.
- **Acceptance.** Dry run on two committed books; inter-rater agreement measured on five books before the panel.
- **Size.** S.

### WP-3.4 Reading-trail report extensions

- **Touches.** `src/cyo_adventure/reading_trail/report.py`, `scripts/report_reading_trail.py`, tests.
- **Adds.** Per decision: choice split and a flag when one option exceeds 90 percent with at least five reads; per
  book: share of reads that saw a payoff (when the book has a plan), stop nodes, rewinds.
- **Constraint.** Owner-only, local output, no route, no export (ADR-030 Decision 6). **Size.** S.

### WP-3.5 Approver: three paths and one quality question

- **Touches.** `src/cyo_adventure/api/review_surface.py`, `src/cyo_adventure/api/approval.py`,
  `src/cyo_adventure/api/schemas.py`, `src/cyo_adventure/db/models.py` plus a migration (one nullable column for the
  answer), `frontend/src/admin/` review detail, regenerated client, tests, `frontend/e2e` admin spec.
- **Behaviour.** The review surface offers three deterministic sampled paths: one through a payoff site with the
  plant, one to a negative ending, one shortest satisfying path. Approval records the answer to one question (D8,
  proposed: "Would you hand this to the child as it is?"). The pitch is shown beside the book for on-demand requests.
  Approval authority and the state machine are unchanged.
- **Acceptance.** Approving without an answer is rejected for books created after the change; existing approval tests
  pass; accessibility lint and the `frontend-e2e` job pass without widening their scope.
- **Size.** M.

### WP-3.6 Demote regex detectors

- **Touches.** `src/cyo_adventure/moderation/agency.py` (advisory wording says "smoke test, low recall"),
  `docs/operations/authoring-guide.md`, `scripts/check_prose_craft.py` help text.
- **Acceptance.** No detector removed; no planning document after this date cites a detector count as evidence of an
  effect. **Size.** S.

### WP-3.7 Plan reviewer: validation, independence rule, exception sampling

- **Goal.** Build the model that approves plans (owner decision D11) and prove it on the project's labelled ground truth
  before anything depends on it. Moved ahead of WP-2.4 on the dependency chain so that its validation runs in
  parallel with WP-2.2 and WP-2.3 and is ready when the plan generator is.
- **Same call as the continuity reader, or a sibling.** A **sibling**: the same provider adapter, validation-set
  format, held-out split and threshold harness, but a separate prompt, module, thresholds and gate. Reasons: the
  inputs differ (a plan, a shape and a fenced request, once per book before any prose exists, against sampled
  `(node, state)` prose passages after fill); the independence rule differs (the plan reviewer must differ from the
  plan's writer, the continuity reader from the fill model); the defect classes and labelled data differ; and one
  failing validation must not switch off the other (G3 and G3b have separate fallbacks). Folding them into one call
  would also make its prompt too broad to validate per class.
- **Touches.** New `src/cyo_adventure/storyplan/review.py` (pure: verdict model, the writer-not-reviewer check, the
  seeded sample draw, the suspension rule); new `src/cyo_adventure/moderation/plan_reviewer.py` (the provider call,
  beside `continuity_reader.py`); new template `src/cyo_adventure/generation/templates/plan_review.md`;
  `src/cyo_adventure/core/config.py` (reviewer model, sample rate, suspended flag, validated-pairing record); new
  `scripts/validate_plan_reviewer.py` and `scripts/review_story_plan.py`; the `plan_review` items of
  `docs/planning/evidence/continuity-reader/validation-set.json` (or a sibling file, decided with WP-3.1); new
  `docs/planning/evidence/plan-reviewer/report.md`; tests. Request text is fenced as untrusted; messages name plan
  entries and never quote story text.
- **Validation set.** The WP-1.3 answer key (`known-defects.json`) and findings files, joined to the WP-1.4 blind plans
  (defective, labelled with the entry's class and severity); the post-fix plans of WP-0.3 and WP-0.4 as clean
  negatives; and, to reach the minimum size D12 sets, plans seeded with one defect each from the WP-1.2 rule witnesses,
  **reported separately as synthetic** and never mixed into the headline figure. Two limits are recorded in the report
  rather than hidden: the answer key holds 17 defect entries, all in the continuity and state classes, and no negatives
  of its own; and it holds nothing on dull or generic plans or plans that miss the request, so those classes have no
  measured recall and the reviewer's verdict on them is advisory until the panel (WP-4.1, WP-4.2) supplies labelled
  data.
- **Behaviour.** The reviewer reads the plan, the shape and the fenced request and returns `pass`, `reject` or
  `unsure` with reasons that name plan entries. A pass is allowed only if the SP checks already passed (the reviewer
  never overrides them). Two runs per plan; a disagreement is `unsure`.
- **Part (a): validation.** Starts after WP-1.5 and WP-3.1, in parallel with WP-2.2 and WP-2.3. Thresholds are fixed
  before the prompt is written (D12). The prompt may be tuned on the tuning half only.
- **Part (b): pairing check.** After the WP-2.3 paid smoke, run the reviewer over those five plans (written by the
  production plan writer) and have the owner or a second agent read them blind, to confirm the validated reviewer
  behaves on the production writer's output and that the writer and reviewer models in use differ.
- **Acceptance.** Meets the D12 thresholds on the held-out half for the named writer, reviewer and prompt; part (b) shows
  no plan the reader judges blocking that the reviewer passed. **Gate G3b.** If it does not after one prompt revision
  on the tuning half, the reviewer is not enabled: plan approval stays with the owner for every plan, WP-2.4 ships
  with the reviewer path disabled, and on-demand generation in the pilot runs with the owner reading every plan.
- **Voiding.** A change of writer model, reviewer model or prompt voids the validation until `validate_plan_reviewer.py`
  passes again for the new pairing; the worker refuses an unvalidated pairing.
- **Depends on.** WP-1.4, WP-1.5, WP-3.1, D12; part (b) also WP-2.3. **Size.** M. **Spend.** 5 to 10 USD (two models,
  two runs, the validation set and the smoke plans).

## 7. Phase 4: pilot

Budget cap for the phase, proposed for D7: **150 USD**, hard stop.

### WP-4.1 Short-request panel, baseline arms

- **Method.** From tag `baseline/pre-story-plan`: 40 jobs on arm (a) skeleton fill and 40 on arm (b) fresh generation,
  production cascade, production defaults, with the harness of WP-0.2. Record delivery, words delivered, cost,
  wall-clock, and the model serving each call.
- **Spend.** 30 to 60 USD at the 0.30 to 0.76 USD per fill measured on 2026-11-20. **Size.** M.

### WP-4.2 Short-request panel, plan-first arm

- **Method.** The same 40 jobs through `plan_fill`. Plans are approved by the WP-3.7 reviewer once G3b has passed. At
  40 plans a 1-in-10 sample is four plans and cannot show drift, so the owner reads **every** plan in this arm (a
  shadow read, proposed for D12), which also gives the reviewer's first live agreement figure. Blind rating with
  WP-3.3; continuity by WP-3.2 plus a hand read of ten books.
- **Kill criterion (pre-registered).** Plan-first replaces skeleton fill for on-demand requests only if all hold:
  delivery rate not lower than arm (a); request fidelity higher on at least two thirds of requests; blind paired
  preference on at least two thirds of pairs; cost no more than three times arm (a). If fidelity rises and delivery
  falls: plan-first for catalog books only. If neither fidelity nor preference moves: the plan layer does not help
  thin prompts; stop and report.
- **Spend.** 20 to 60 USD, to be narrowed by WP-2.6's measurement. **Owner time.** 2 to 4 hours for the shadow plan
  reads, which D7 should include. **Depends on.** WP-2.4, WP-2.6, WP-3.3. **Size.** M.

### WP-4.3 Ten-book pilot

- **Method.** Three retained shapes, ten plan-first books whose plans pass the WP-3.7 reviewer and are also read by the owner (shadow, as in WP-4.2), including
  `the-clockwork-menagerie` and a 10-13 shape so the 2026-11-20 baselines apply. Hand counts of seams, recaps and
  label defects; an independent human continuity read of every book; blind paired read against the committed fills of
  the same shells.
- **Kill criterion (pre-registered).** Fail if an independent read finds a route-fact contradiction in more than two
  of ten books, or blind readers do not prefer the new book in at least seven of ten pairs.
- **Owner time.** Ten plan approvals and the blind reads: estimated 8 to 12 hours. **Spend.** 10 to 30 USD. **Size.**
  L.

### WP-4.4 Decision report

- **Output.** `docs/planning/story-plan-pilot-report.md` with the pre-registered criteria, the results, and one of:
  adopt for both paths; adopt for catalog only; stop. ADR-033 moves to Accepted, is amended, or is withdrawn
  accordingly. **Owner decision.** D10.

## 8. Later

Each stays `blocked` on WP-4.4 in the register (Appendix B, `UW-G39`).

| Item | What | Why later |
| --- | --- | --- |
| L-1 | Conditional passage text in the Storybook schema (ADR-025 minor; both engines, offline, validator walk, moderation fan-out) | Large; inserted arrival nodes work meanwhile |
| L-2 | Rule registry rendered into the compiler, the drafting guide, the skill and the review surface (closes AL-780) | The compiler's in-module table is enough for the pilot |
| L-3 | Lesson triage by layer; one summary row per run | Changes a `CLAUDE.md` rule; owner's call |
| L-4 | Supersede-edition in publishing (`UW-M14`) | Catalog delivery works by import |
| L-5 | Generating shapes under the strict checks | Needs the pilot's evidence that shape plus plan works |
| L-6 | Cross-book diversity, reopened with reader data | Not observable until families own many books |
| L-7 | 3-5 and 5-8 | These bands mostly behave; leave alone |
| L-8 | Resume or retire `mutation/` and `flywheel/` | Depends on L-5 |

## 9. Evidence gates

| Gate | After | Passes when | If not |
| --- | --- | --- | --- |
| G0 | WP-0.4 | every family-test book has a plan and a clean second read | the book is held back from the session |
| G1 | WP-1.5 | the pass criterion of WP-1.5 | one revision, then stop |
| G2 | WP-2.6 | five smoke books delivered within 10 percent of commissioned words; cost and latency measured | fix or re-scope before Phase 4 budgets are set |
| G3 | WP-3.2 | reader meets D6 thresholds on held-out data | reader stays offline; pilot uses human reads only |
| G3b | WP-3.7 | reviewer meets the D12 thresholds on held-out data for the named writer, reviewer and prompt | reviewer not enabled; the owner approves every plan; WP-2.4 ships with the reviewer path off |
| G4 | WP-4.2, WP-4.3 | the pre-registered criteria | restrict to catalog, or stop |

## 10. Dependencies and critical path

```text
D2 -> 0.1
D3 (7 books) -> 0.3 -> 0.4 -> [G0: family test]   0.5 (parallel)   0.2 (parallel)
              |
              v
D1 -> 1.1 -> 1.2 ---------.
      0.4 -> 1.3 -> 1.4 ---+-> 1.5 [G1] -- D5
                  |              |
                  |              +-> 3.1 (D6) -> 3.2 [G3]
                  |              |    3.3, 3.4, 3.6 (parallel)   3.5 (D8)
                  |              |       |
                  +--------------+-> 3.7a (D11 made, D12; needs 1.4, 1.5, 3.1) -----.
                                 |                                                   |
        2.1, 2.7 (independent)   v                                                   v
                       D4 -> 2.2 -> 2.3 -> 3.7b (pairing check) -> [G3b] ---------> 2.4
                                     |                                               |
                              D9 ->  2.5 -> 2.6 [G2]                                 |
                                             |                                       |
      D7 -> 4.1 (any time after 0.2)         +-------------> 4.2 <------------------+
                                                              |   (4.2 also needs 3.3)
                                                              v
                                                       4.3 -> 4.4 [G4] -- D10
```

**Critical path:** 0.3, 0.4, 1.3, 1.4, 1.5, 2.2, 2.3, 2.5, 2.6, 4.2, 4.3, 4.4. WP-1.1 and WP-1.2 run alongside 0.4 to
1.4 and must finish before 1.5. Phase 3 runs alongside Phase 2 and must finish before 4.2.

**Effect of D11 (2026-11-21).** The critical path is unchanged in membership. WP-2.4 now waits on WP-3.7 (G3b), which
makes a new chain 1.5, 3.7a, 3.7b, 2.4, 4.2 that runs beside 2.5 and 2.6 and joins at 4.2. It is near-critical rather
than critical: 3.7a (size M) starts the moment 1.5 passes and has the length of 2.2 and 2.3 to finish in, and 3.7b needs
only the five WP-2.3 smoke plans, so 2.4 is ready by the time 2.6 is. It becomes critical if 3.7a needs more than one
prompt revision or if the validation set cannot reach D12's minimum size. WP-4.3's catalog plans do not wait on it,
since the owner reads them all in the pilot; only the on-demand arm (4.2) does.

## 11. Estimates

All untested. Ranges are the author's judgment; treat them as plus or minus 50 percent until the named package
reports.

| Phase | Effort (agent working days) | Spend (USD) | Firmed up by |
| --- | --- | --- | --- |
| 0 | 5 to 8 | 0 | WP-0.3 (plan size and time per book) |
| 1 | 6 to 10 | 0 | WP-1.4 (extraction time, agreement) |
| 2 | 15 to 25 | 20 to 45 | WP-2.3 (plan yield), WP-2.6 (tokens, cost, latency) |
| 3 | 9 to 14 | 10 to 20 | WP-3.2, WP-3.7 |
| 4 | 6 to 9, plus 8 to 12 owner hours | 60 to 150 (capped at 150) | WP-4.1 |
| Total | 41 to 66 | 90 to 215 | |

Phase 3 grew by WP-3.7 (2 to 3 agent days and 5 to 10 USD) when D11 was made; WP-2.4 stays inside size M. Phase 4 owner
time gains 2 to 4 hours for the shadow plan reads (WP-4.2), outside the agent-day and spend figures.

Calendar time depends on how many packages run in parallel and on owner turnaround at D1, D4, D5, D7 and D12; with two
agents and prompt decisions, six to nine weeks is plausible and is not a commitment.

## 12. Risks

| Risk | Likelihood | Effect | Mitigation |
| --- | --- | --- | --- |
| The retrospective cannot be made non-circular (the extractor has seen the defects) | medium | G1 means nothing | WP-1.4's committed prompt and a fresh agent; two extractions of one book |
| The Lighthouse blockers were not in the repo | low (resolved) | weaker known-answer set | Written down in `docs/planning/evidence/structural-verification-2026-11-20/lighthouse-continuity-read.md` (B1 to B3, S1 to S4); WP-1.3 cites it. Residual risk: they were recorded after the fact, so G1 still pairs them with the documented Run B defects |
| Plans from one line are generic | medium | coherent, dull books | pitch step with required want and obstacle; WP-4.2 measures; kill criterion |
| Plan strings carry injected or unsafe text into prompts | low to medium | safety | SP-9 floors, classifier screening, fencing; test with the adversarial harness |
| Scene-by-scene cost is far above the estimate | medium | budget | G2 measures before Phase 4 budgets; three-times cap in the kill criterion |
| The continuity reader fails validation | medium | no automated continuity signal on demand | G3 fallback: offline script, human path reads |
| Two fill paths double maintenance | high | drag | WP-4.4 decides; v1 untouched meanwhile |
| Owner time is the bottleneck | high | calendar | plans are approved by the validated reviewer and read by the owner by exception (D11); decisions batched (section 13) |
| The plan reviewer shares the plan writer's blind spots, so a plan with a defect neither sees is approved | medium | a wasted fill; at worst a book the owner then rejects (plan approval is not the safety gate) | a different model from the writer, enforced in code; no use before validation against the labelled set (G3b, D12); a random sample read by the owner so drift is noticed, with suspension on overturns; fail-closed on error or disagreement; per-class authority, since classes without labelled data stay advisory |
| The labelled set is too small or too narrow to validate the reviewer (17 defect entries, no negatives of its own, no plan-quality classes) | high | G3b cannot be passed honestly, or passes on synthetic data | minimum size set in D12; seeded-defect plans reported separately as synthetic; fallback is the owner approving every plan, which is the status before D11 and costs only owner time; the panel adds labelled data for request fidelity |
| The family test slips behind this work | low | product | Phase 0 touches only the family books; nothing in Phases 1 to 4 is on its path |

## 13. Owner decisions

Dates are proposals from 2026-11-21; each is also stated as the package it blocks, which is the real deadline.

| Id | Decision | Blocks | Proposed by |
| --- | --- | --- | --- |
| D1 | Ratify ADR-033 (or return it). **Ratified 2026-11-21** (owner, in session) | WP-1.1 merging to `main` | 2026-11-28 |
| D2 | Confirm the freeze list in WP-0.1. **Approved 2026-11-21** (owner, in session) | WP-0.1 | 2026-11-24 |
| D3 | Family-test book list; enable reading-trail capture for the session. **Decided 2026-11-21** (owner, in session): see the note below | WP-0.3, WP-0.5 | 2026-11-24 |
| D4 | The retained shell set (eight to twelve, two per offered cell) | WP-2.2 | when G1 passes |
| D5 | Accept the G1 verdict. **Decided 2026-11-21** (owner, in session): G1 failed as scored ([report](./evidence/story-plan-retro/report.md)); take the single permitted revision and one re-run. The SP-9 length change made before the first run (`29c0ff8`) does not count as the revision. Revision scope: `AL-817` to `AL-819` and `AL-822` (SP-4 independent of which half of a thread is declared the plant, SP-4 exempts endings, SP-8 symmetric opportunity costs, SP-9 'wound' homograph, state negations recorded at the asserting node), plus `AL-821`. Fresh blind re-extraction of the scored books; the criterion and answer key are unchanged. A second failure stops Phase 2 **Re-run verdict accepted 2026-11-21** (owner, in session): G1 passes ([re-run report](./evidence/story-plan-retro/rerun/report.md)), on two conditions. (1) The plan-writing conventions of ADR-033 Decision 1 bind every plan, hand-written or generated. (2) The WP-0.4 second read stays the standing continuity control for catalog books until the fresh-corpus confirmation (WP-1.6) passes; the pass was earned after a revision designed with the answer key in view, so it is weaker evidence than a first-time pass. Phase 2 may start | all of Phase 2 | done |
| D6 | Continuity reader thresholds (decide with D12, which reuses the same split and harness) | WP-3.2 | before WP-3.2 starts |
| D7 | Phase 4 budget (proposed cap 150 USD) and the kill criteria as written | WP-4.1 | before WP-4.1 starts |
| D8 | Wording of the approver's quality question; mandatory or not | WP-3.5 | before WP-3.5 starts |
| D9 | Per-band recap rule (AL-767) | WP-2.5 | before WP-2.5 starts |
| D10 | Adopt for both paths, catalog only, or stop | everything in section 8 | on WP-4.4 |
| D11 | Plans, for catalog and on-demand, are approved by a validated plan-review model (a different model from the writer, validated against the labelled ground truth before use); the owner reviews by exception, every reject and "unsure" plus a random sample. Amends ADR-033 Decision 3. **Made 2026-11-21** (owner, in session; see the note below) | WP-2.4, WP-3.7 | made |
| D12 | Plan-reviewer thresholds, exception-sample rate and suspension rule (decided alongside D6). Proposed values and reasons in the note below | WP-3.7 | before WP-3.7 starts |

**D3 as decided on 2026-11-21 (owner, in session).**

- **Seven books go to the children.** Four revised: `the-sky-ship-stowaway` (8-11), `the-hollow-lighthouse` (10-13),
  `the-midnight-museum` (10-13), `the-signal-in-the-static` (13-16). Three unrevised controls: `the-cave-of-echoes`
  (8-11, the original edition; the partial revision on branch `wt/book-cave` stays parked), `the-mapmakers-island`
  (10-13), `the-vanishing-orchard` (13-16). The comparison is revised against control, per band.
- **Controls** get a plan and a continuity read. Only plain contradictions are fixed in them, never agency problems,
  so they stay valid controls (WP-0.4).
- **Pairing notes for the owner.** `the-mapmakers-island` and `the-signal-in-the-static` both have a hero named
  Wren, and `the-vanishing-orchard` and `the-hollow-lighthouse` both open on a last bus: give each of those pairs to
  different children where possible, so one child does not blur two books.
- **Edit pause lifted for these seven books only** (`UW-M20`): WP-0.4 fixes may proceed on them; all other book
  editing stays paused.
- **Reading-trail capture is to be turned on** for the family tier (WP-0.5; owner step in the checklist, `B6`).

**D11 as decided on 2026-11-21 (owner, in session).** Story Plans are approved by a validated plan-review model instead
of by the owner, for catalog books and on-demand requests.

- A plan is approved when SP-0 to SP-9 pass, screening is clean, and the plan-review model passes it.
- The reviewer is a different model from the one that wrote the plan, and may not be used until it is validated against
  the labelled ground truth (the frozen `known-defects.json` and the findings files beside it) at thresholds the owner
  sets (D12).
- The owner reviews by exception: every plan the model rejects or is unsure about, plus a random sample.
- Final approve-and-publish of every book by the owner (ADR-005) and the rule that nothing generated is shown to a child
  (ADR-015) are unchanged. Plan approval is a quality gate, not the safety gate.
- Consequences recorded here: WP-2.4 depends on a validated reviewer; WP-3.7 is new; the effort and spend totals,
  critical path, gates and risk table are updated; the pilot reads every plan in shadow because its volume is too low
  for a sample to measure drift. ADR-033 carries the amendment note.

**D12 as proposed (not yet decided).** One decision, taken with D6 because both use the WP-3.1 split and harness.
Values are the proposer's choice and are the owner's to change; each is explained.

| Item | Proposed | Why |
| --- | --- | --- |
| Defect recall, held-out half | reject or `unsure` on at least 90 percent of labelled defective plans, and on every blocker-severity entry | the costly error is a pass on a defective plan (a wasted fill, a bad book for the owner to read); blockers are the defects the family-test books actually carried. Higher than D6's 0.8 because a plan reviewer sees a short structured document, and because a miss here is passed unseen where a continuity-reader miss is still read by the approver |
| Flag rate on clean plans | reject or `unsure` on at most 20 percent | flags are owner time. With a 10 percent sample the owner then reads at most about 28 percent of plans; above that, "by exception" stops being true |
| Run agreement | identical verdicts on at least 90 percent of plans across two runs | the same bar as D6, and a disagreement is routed as `unsure` anyway |
| Minimum validation size | at least 15 defective and 15 clean held-out plans, supplemented with seeded-defect plans reported as synthetic | the answer key has 17 defect entries and no negatives, so about half that are held out; on 15 cases a measured 0.9 is statistically close to 0.7, and the report must show the counts and intervals so the owner decides knowing it. If the minimum cannot be met the reviewer is not validated |
| Sample rate | 1 in 10 in steady state; 100 percent through the pilot (WP-4.2, WP-4.3) | at pilot volume (about 50 plans) a 1-in-10 sample is five plans and measures nothing; reading all of them is cheap and gives the first live agreement figure |
| Suspension | the owner overturns any blocker-class pass, or more than 1 in 5 of the last 10 sampled passes (at least 5 sampled) | a defined trigger for sending every plan back to the owner and revalidating, instead of drift being noticed by feel |
| Scope of authority | per defect class: only classes with measured recall; others advisory | the labelled set has no plan-quality classes, so claiming authority over them would be unmeasured |

## Appendix A: mapping to existing planning identifiers

| WP | Capability ids | Roadmap home | Existing rows touched |
| --- | --- | --- | --- |
| 0.1 | A11 | `content` | `UW-C494`, `UW-C499`, `UW-G12`, `UW-C315` (see Appendix B) |
| 0.2, 3.3, 4.1, 4.2 | K11, G4, K19, A10 | `content` | `UW-C309` |
| 0.3, 0.4 | K3, A11 | `content` | `UW-C493` (AL-790), AL-773, AL-788 |
| 0.5, 3.4 | A7 | `now` | none |
| 1.1 to 1.5 | S3, S4, A11 | `content` | `UW-C498` (AL-799), AL-800 |
| 2.1 | K3, K11 | `content` | none |
| 2.2, 2.5 | A11, S3 | `content` | `UW-C496` (AL-797), `UW-C497` (AL-798), AL-780 |
| 2.3, 2.4 | K11, G4, A10, A6 | `content` | none; WP-2.4 waits on WP-3.7 (D11) |
| 2.6 | A7, A8 | `content` | `UW-C500` (AL-801), `UW-C269` |
| 2.7 | A11 | `content` | AL-771, AL-785 |
| 3.1, 3.2, 3.6 | A11, G5 | `content` | `UW-C495` (AL-796), `UW-C479` |
| 3.5 | G5, A6 | `content` | AL-764 (open half) |
| 3.7 | A11, G5, A6 | `content` | none |
| 4.3, 4.4 | K3, A10 | `content` | none |
| L-4 | G6 | `content` | `UW-M14` |

The SQ plan (`story-structure-improvement-plan.md`) is not edited by this plan. SQ-11 to SQ-14 (alternate beats and
variants) are expected to be overtaken if G4 passes; that disposition is the owner's at D10.

## Appendix B: register and lessons-log changes for the orchestrator to apply

The drafting agent did not edit the register or the lessons log. Ids below were the next free ones at drafting time (`A`
ended at 63, `G` at 27). **Applied 2026-11-21:** the ids were still free, so `UW-A64` and `UW-G28` to `UW-G42` were
created unrenumbered. Existing rows below received dated notes recording the proposed disposition rather than a status
change, because each disposition's evidence (ADR-033 ratified, or a work package's commits) does not exist yet; the
status changes are applied when that evidence lands. The Lighthouse blockers are now written down, so no row below
depends on their absence. Every existing-row change must be checked against the row's
current text before it is applied.

**Proposed new rows.**

| Id | Cluster | Item | Phase | Status |
| --- | --- | --- | --- | --- |
| UW-A64 | A | Owner ratification of ADR-033 (the Story Plan meaning layer). Owner: core-maintainer. | content | decision |
| UW-G28 | G | WP-0.1: freeze mutation, flywheel, retrofit promotion, strict remediation, diversity rounds and paid prompt A/B; add the three status banners. | content | unscheduled |
| UW-G29 | G | WP-0.3 and WP-0.4: hand-written plans and a second-reader continuity pass for each family-test book. | content | unscheduled |
| UW-G30 | G | WP-1.1 to WP-1.5: Story Plan schema, SP-1 to SP-9, and the retrospective gate G1. | content | unscheduled |
| UW-G31 | G | WP-2.1: unpin `tier` and `structure_pattern` in `brief.py` for 8-11 and up. | content | unscheduled |
| UW-G32 | G | WP-2.2 and WP-2.5: retained shapes, v2 typed directives, the directive compiler. Blocked on G1 and D4. | content | blocked |
| UW-G33 | G | WP-2.3 and WP-2.4: pitch and plan generation, persistence, approval policy. Blocked on G1. | content | blocked |
| UW-G34 | G | WP-2.6: scene-by-scene fill with ledger context. Blocked on `UW-G32`. | content | blocked |
| UW-G35 | G | WP-3.1 and WP-3.2: continuity reader and its validation set. Blocked on G1. | content | blocked |
| UW-G36 | G | WP-0.2, WP-3.3, WP-4.1, WP-4.2: short-request panel and request-fidelity measure. | content | unscheduled |
| UW-G37 | G | WP-3.5: approver path sampling and one recorded quality question. | content | unscheduled |
| UW-G38 | G | WP-4.3 and WP-4.4: ten-book pilot and decision report. Blocked on `UW-G34` and `UW-G35`. | content | blocked |
| UW-G39 | G | Later items L-1 to L-8. Blocked on the WP-4.4 decision. | content | blocked |
| UW-G40 | G | WP-2.7: reading-level measure fix (AL-771, AL-785). | content | unscheduled |
| UW-G41 | G | WP-0.5 and WP-3.4: family-test instrumentation and reading-trail report extensions. | now | unscheduled |
| UW-G42 | G | WP-3.6: label the regex agency detectors as smoke tests. | content | unscheduled |
| UW-G43 | G | WP-3.7: plan reviewer (a different model from the writer), its validation against the labelled ground truth, its independence rule and exception sampling. Added 2026-11-21 with owner decision D11. Blocked on `UW-G30` (WP-1.4, WP-1.5) and decision D12. | content | blocked |

**Proposed changes to existing rows** (disposition and the evidence it needs).

| Row | Proposed disposition | Evidence required before applying |
| --- | --- | --- |
| `UW-C493` (AL-790) | done when WP-0.4 lands for all family books (the blockers themselves are recorded in the Lighthouse read file) | the findings files and commits |
| `UW-C495` (AL-796) | `blocked` on `UW-G35`; close as superseded if G3 passes | the WP-3.2 validation report |
| `UW-C496` (AL-797), `UW-C497` (AL-798) | keep; re-scope to shells not converted to v2; superseded for converted shells by `UW-G32` | the WP-2.2 conversion commits |
| `UW-C498` (AL-799) | `blocked` on `UW-G30`; superseded by SP-4 and SP-6 if G1 passes | the WP-1.5 report |
| `UW-C499` (AL-800) | `blocked` on the D10 decision (retrofit promotion is frozen) | ADR-033 ratified |
| `UW-C494` (AL-794, AL-795) | `blocked` on the D10 decision | ADR-033 ratified |
| `UW-C500` (AL-801) | keep; closed for the new path by WP-2.6, still open for `fill_skeleton` | the WP-2.6 commit |
| `UW-C479` (AL-764, AL-765) | re-scope: the budget half is replaced by WP-3.5 and WP-3.6 | those commits |
| `UW-M14` | unchanged; listed under L-4 | none |
| `UW-G12`, `UW-C315` | `blocked` on the D10 decision | ADR-033 ratified |

**Lessons log.** No rows are proposed by this plan: it reports no fill pass, gate change or rater-instrument change.
AL-773, AL-783, AL-788, AL-790, AL-796 to AL-800 stay `open` until the package named in Appendix A lands and can be
cited as `Ref`. Marking any of them `superseded` needs that reference.
