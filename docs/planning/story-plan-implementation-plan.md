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

> **Status**: draft for owner approval, 2026-11-21. **Decision record**:
> [ADR-033](./adr/adr-033-story-plan-meaning-layer.md) (Proposed). **Source**: [architecture review,
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
| 2.4 | Plan approval: catalog by owner, on-demand automatic | M | none | no |
| 2.5 | Directive compiler and single scene template | L | 5 to 10 USD | D9: recap rule per band |
| 2.6 | Scene-by-scene fill with ledger context | L | 10 to 20 USD | no |
| 2.7 | Reading-level measure fix | S | none | no |
| 3.1 | Reader validation set and thresholds | S | none | D6: thresholds |
| 3.2 | Continuity reader stage | M | 5 to 10 USD | no |
| 3.3 | Request-fidelity measure | S | none | no |
| 3.4 | Reading-trail report extensions | S | none | no |
| 3.5 | Approver: three paths and one quality question | M | none | D8: wording |
| 3.6 | Demote regex detectors to smoke tests | S | none | no |
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
- **Touches.** New `out/<slug>.plan.json` for each of `the-hollow-lighthouse`, `the-sky-ship-stowaway`,
  `the-midnight-museum`, `the-signal-in-the-static` (and `the-sunken-signal` if D3 includes it). Nothing else.
- **Method.** Per book: cast with wants and voices; the truth; facts with ids; per node `establishes` and `requires`
  as the prose actually has them; threads from the declared variables; ending gifts. Record facts as written,
  including any that contradict each other: do not tidy the book while writing its plan.
- **Outputs.** The plan files, and a short note per book of how long it took and how many facts and threads it needed.
  **This is the first measurement of plan size and authoring time**, which sections 11 and WP-2.3 depend on.
- **Acceptance.** Every node and choice id in the book appears in its plan; JSON parses; a second agent can answer
  "what does the reader know on entering node X" from the plan alone for ten sampled nodes.
- **Depends on.** D3. **Size.** M (the review's guess is two to four hours per book; untested).

### WP-0.4 Second-reader continuity pass and fixes

- **Goal.** Close AL-790 for the books the children will read, and create labelled defect data.
- **Touches.** The same `out/<slug>.filled.json` and `.plan.json` files; new
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
- **Acceptance.** Zero open findings per book; findings files committed; gate and `check_fill_integrity.py` pass on
  each revised book.
- **Gate (family test).** A book goes to the children only with a plan and a clean second read.

### WP-0.5 Family-test instrumentation and debrief

- **Goal.** Decide before the session what will be looked at.
- **Touches.** `docs/planning/r1-live-e2e-checklist.md` (family-session section); environment setting
  `READING_TRAIL_ENABLED` (owner action, D3).
- **Outputs.** A five-question spoken debrief; the list of signals to read from `scripts/report_reading_trail.py`
  (finish rate, stop nodes, choice split per decision, rewinds, endings reached, replays). Output stays on the owner's
  machine (ADR-030 Decision 6).
- **Acceptance.** Checklist updated; one dry run of the report against a local database.

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

- **Touches.** `src/cyo_adventure/story_requests/authoring_plan.py` (policy default with admin override in place of a
  per-request click), `src/cyo_adventure/generation/worker.py` (auto-approve on clean checks; route to `needs_review`
  otherwise), `src/cyo_adventure/events/` (two event types), `docs/operations/authoring-guide.md`. No frontend in
  version 1.
- **Behaviour.** Catalog: the plan file is approved by review of its pull request; `scripts/check_story_plan.py` runs
  in pre-commit on `out/*.plan.json`. On-demand: automatic when SP-1 to SP-9 pass and screening is clean. Nothing is
  shown to the requester.
- **Acceptance.** An on-demand job with a failing plan never reaches the fill stage; the audit event records which
  checks passed and the plan hash; final approve-and-publish is unchanged (`publishing/` untouched, asserted by its
  existing tests).
- **Depends on.** WP-2.3. **Size.** M.

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

## 7. Phase 4: pilot

Budget cap for the phase, proposed for D7: **150 USD**, hard stop.

### WP-4.1 Short-request panel, baseline arms

- **Method.** From tag `baseline/pre-story-plan`: 40 jobs on arm (a) skeleton fill and 40 on arm (b) fresh generation,
  production cascade, production defaults, with the harness of WP-0.2. Record delivery, words delivered, cost,
  wall-clock, and the model serving each call.
- **Spend.** 30 to 60 USD at the 0.30 to 0.76 USD per fill measured on 2026-11-20. **Size.** M.

### WP-4.2 Short-request panel, plan-first arm

- **Method.** The same 40 jobs through `plan_fill`. Blind rating with WP-3.3; continuity by WP-3.2 plus a hand read of
  ten books.
- **Kill criterion (pre-registered).** Plan-first replaces skeleton fill for on-demand requests only if all hold:
  delivery rate not lower than arm (a); request fidelity higher on at least two thirds of requests; blind paired
  preference on at least two thirds of pairs; cost no more than three times arm (a). If fidelity rises and delivery
  falls: plan-first for catalog books only. If neither fidelity nor preference moves: the plan layer does not help
  thin prompts; stop and report.
- **Spend.** 20 to 60 USD, to be narrowed by WP-2.6's measurement. **Size.** M.

### WP-4.3 Ten-book pilot

- **Method.** Three retained shapes, ten plan-first books with owner-approved plans, including
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
| G4 | WP-4.2, WP-4.3 | the pre-registered criteria | restrict to catalog, or stop |

## 10. Dependencies and critical path

```text
D2 -> 0.1
D3 -> 0.3 -> 0.4 -> [G0: family test]        0.5 (parallel)        0.2 (parallel)
              |
              v
D1 -> 1.1 -> 1.2 ---------.
      0.4 -> 1.3 -> 1.4 ---+-> 1.5 [G1] -- D5
                                  |
        2.1, 2.7 (independent)    v
                       D4 -> 2.2 -> 2.3 -> 2.4
                                     |
                              D9 ->  2.5 -> 2.6 [G2]
                                             |
      1.5 -> 3.1 (D6) -> 3.2 [G3]            |
             3.3, 3.4, 3.6 (parallel)        |
             3.5 (D8)                        v
                    D7 -> 4.1 (any time after 0.2)   4.2 -> 4.3 -> 4.4 [G4] -- D10
```

**Critical path:** 0.3, 0.4, 1.3, 1.4, 1.5, 2.2, 2.3, 2.5, 2.6, 4.2, 4.3, 4.4. WP-1.1 and WP-1.2 run alongside 0.4 to
1.4 and must finish before 1.5. Phase 3 runs alongside Phase 2 and must finish before 4.2.

## 11. Estimates

All untested. Ranges are the author's judgment; treat them as plus or minus 50 percent until the named package
reports.

| Phase | Effort (agent working days) | Spend (USD) | Firmed up by |
| --- | --- | --- | --- |
| 0 | 5 to 8 | 0 | WP-0.3 (plan size and time per book) |
| 1 | 6 to 10 | 0 | WP-1.4 (extraction time, agreement) |
| 2 | 15 to 25 | 20 to 45 | WP-2.3 (plan yield), WP-2.6 (tokens, cost, latency) |
| 3 | 7 to 11 | 5 to 10 | WP-3.2 |
| 4 | 6 to 9, plus 8 to 12 owner hours | 60 to 150 (capped at 150) | WP-4.1 |
| Total | 39 to 63 | 85 to 205 | |

Calendar time depends on how many packages run in parallel and on owner turnaround at D1, D4, D5 and D7; with two
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
| Owner time is the bottleneck | high | calendar | plan approval only for catalog; decisions batched (section 13) |
| The family test slips behind this work | low | product | Phase 0 touches only the family books; nothing in Phases 1 to 4 is on its path |

## 13. Owner decisions

Dates are proposals from 2026-11-21; each is also stated as the package it blocks, which is the real deadline.

| Id | Decision | Blocks | Proposed by |
| --- | --- | --- | --- |
| D1 | Ratify ADR-033 (or return it) | WP-1.1 merging to `main` | 2026-11-28 |
| D2 | Confirm the freeze list in WP-0.1 | WP-0.1 | 2026-11-24 |
| D3 | Family-test book list; enable reading-trail capture for the session | WP-0.3, WP-0.5 | 2026-11-24 |
| D4 | The retained shell set (eight to twelve, two per offered cell) | WP-2.2 | when G1 passes |
| D5 | Accept the G1 verdict | all of Phase 2 | within two days of WP-1.5 |
| D6 | Continuity reader thresholds | WP-3.2 | before WP-3.2 starts |
| D7 | Phase 4 budget (proposed cap 150 USD) and the kill criteria as written | WP-4.1 | before WP-4.1 starts |
| D8 | Wording of the approver's quality question; mandatory or not | WP-3.5 | before WP-3.5 starts |
| D9 | Per-band recap rule (AL-767) | WP-2.5 | before WP-2.5 starts |
| D10 | Adopt for both paths, catalog only, or stop | everything in section 8 | on WP-4.4 |

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
| 2.3, 2.4 | K11, G4, A10, A6 | `content` | none |
| 2.6 | A7, A8 | `content` | `UW-C500` (AL-801), `UW-C269` |
| 2.7 | A11 | `content` | AL-771, AL-785 |
| 3.1, 3.2, 3.6 | A11, G5 | `content` | `UW-C495` (AL-796), `UW-C479` |
| 3.5 | G5, A6 | `content` | AL-764 (open half) |
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
