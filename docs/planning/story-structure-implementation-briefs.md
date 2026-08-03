---
schema_type: planning
title: "Story Structure Improvement: Implementation Briefs (SQ-01..SQ-24)"
description: "Per-deliverable implementation briefs for story-structure-improvement-plan.md, written
  for a team that has never touched this codebase: current behavior with file and function anchors,
  change specification, test plan, and definition of done for each SQ item, plus team onboarding and
  the non-negotiable project conventions."
tags:
  - planning
  - generation
  - diversity
  - storybook
status: active
owner: core-maintainer
authors:
  - name: "Claude (planning session, branch claude/story-structure-diversity-ba8swy)"
purpose: "Make the improvement plan executable by a new implementation team without archaeology: every
  brief names the exact modules, functions, and contracts it touches, what exists today, what changes,
  and how the change is proven."
component: Strategy
source: "story-structure-improvement-plan.md (the schedule and gates); story-structure-diversity-
  critical-analysis.md (the evidence); direct code verification on commit 36b32bc plus this branch.
  Line numbers cited below are as of commit 36b32bc and are anchors, not contracts; trust the named
  function over the number if they drift."
---

# Story Structure Improvement: Implementation Briefs

Read [story-structure-improvement-plan.md](story-structure-improvement-plan.md) first for the stages,
critical path, owner gates, and capacity rules. This document is the per-deliverable detail.

## 0. Team onboarding (read this before writing code)

### 0.1 Required reading, in order

1. `CLAUDE.md` (root): project conventions. Non-negotiables repeated in 0.3.
2. [story-structure-diversity-critical-analysis.md](story-structure-diversity-critical-analysis.md):
   why this work exists. Sections 2.5, 2.6, 2.7, and 5 are the ones implementation decisions lean on.
3. [story-diversity-plan-v2.md](story-diversity-plan-v2.md) section 1 (the verified fact base) and
   the A1-A8 rows (what is already delivered; do not rebuild it).
4. `docs/architecture/story-skeletons.md` and `docs/architecture/generation-pipeline.md`: the domain
   model and pipeline shape.
5. ADR-011 (scale framework), ADR-019 (theme contracts), ADR-020 (mutation/catalog growth), ADR-026
   (rendered stops). Skim the rest of `docs/planning/adr/`.
6. [research/README.md](research/README.md): which constants are evidence-backed vs designer priors.
7. [capability-register.md](capability-register.md): the persona capability contract. This program
   serves K3 (structural and state/consequence story variety) among others; any SQ item that changes
   a reader- or guardian-facing capability cites the register ID(s) it serves in its PR, per the
   register's contract.

### 0.2 Environment

```bash
uv sync --all-extras && uv run pre-commit install     # backend
(cd frontend && npm install)                          # frontend (only some briefs touch it)
uv run pytest --cov=src --cov-fail-under=80           # the coverage floor is part of done, not extra
uv run ruff check . && uv run basedpyright src/       # both must stay clean
uv run bandit -c pyproject.toml -r src                # security scan, required before commit
pre-commit run --all-files                            # hooks must pass locally, not only on push
uv run mkdocs build                                   # strict; required for any docs/ change
```

Every command above maps to a definition-of-done requirement in 0.4; none is optional.

### 0.3 Non-negotiable conventions (enforced by hooks/CI, will block you)

- Feature branches per item (`feat/sq-07-selection-rebalance` style); never work directly on `main` or `develop`.
- Conventional Commits; signed commits (`git commit -S`); no em-dash characters anywhere.
- RAD tags (`#CRITICAL` / `#ASSUME` / `#EDGE` with `#VERIFY`) on assumptions in the mandatory
  categories (timing, external resources, data integrity, concurrency, security).
- **Backend contract changes regenerate the frontend client**: any route or Pydantic model change
  requires `cd frontend && npm run generate-client` with the diff committed; CI fails on drift.
- **Authoring lessons log**: any authoring run, fill pass, or validator change made in service of
  authoring MUST append qualifying lessons to `docs/planning/authoring-lessons-log.md` (validated by
  `scripts/check_lessons_log.py`; open lessons need a register row, `scripts/check_work_linkage.py`).
- **Safety invariants that no brief may violate**: content never bypasses the validator gate plus
  human approval (ADR-005); the 12-value echo vocabulary in `diversity/normalize.py::_THEME_TAG_MAP`
  is frozen (kid-facing, `#CRITICAL`); no premise text crosses a family boundary or enters a prompt
  outside the `UNTRUSTED_USER_INPUT` fence; selection weights never reach zero (decision C-4);
  `generation/binding.py` stays fail-closed.

### 0.4 Definition-of-done template (applies to every brief unless it overrides)

Code + tests merged with quality gates green (pytest with coverage floor, ruff, basedpyright, bandit);
acceptance check from the plan's table demonstrated in a committed test or committed report; register
row(s) updated with a Ref when the brief closes one; lessons appended if any qualified.

---

## Stage 0 briefs

### SQ-01: Ship the inventory

**Status quo.** 23 validator-passed filled books (plus 2 pilot re-themes; 25 total) were authored and
are listed in [draft-stories-manifest.md](draft-stories-manifest.md). Import tooling is built:
`src/cyo_adventure/generation/import_catalog.py` (async `import_catalog(...)` with an argparse CLI,
imports under `CATALOG_FAMILY_ID` and leaves stories at `in_review` or `needs_revision`; a re-run is
idempotent and reports `skipped_existing` for rows already present) and
`src/cyo_adventure/publishing/catalog_publish.py::promote_catalog_story` (per-story admin promotion to
`visibility='catalog'`). An import run against production is recorded by issue #347 (opened
2026-07-21): its Summary says it was "Surfaced while importing the 25 hand-authored catalog stories
into production (`cyo_adventure.generation.import_catalog`)", and its Context section says "Discovered
during the ADR-021 production catalog seed (25 stories to `in_review`)"; the stories it discusses were
committed at `in_review`, not blocked by the warnings it reports. What that run's rows look like in a
live database today (still present, still `in_review`, re-touched by something else) is not established
here; verifying current state is the runbook's first step below, not an assumption of this brief. What
is certain independent of that run's fate: `import_catalog.py` never publishes by design, so even a
fully successful, still-intact import leaves every book unreachable by a kid profile until an admin
runs `promote_catalog_story`. That promotion step is the open gap, not the import step; nothing on
record shows it has run for this inventory. Imported books are re-moderated, not trusted (#529/#537
landed the admin re-moderation entry point and catalog sweep script).

Note for the runbook author: issue #347 also carries four open questions surfaced by that 2026-07-21
run (Q1: a review stage was making billed OpenRouter calls under a nominally-mock provider, because
`review_provider`/`generation_provider` settings bind only their `CYO_ADVENTURE_`-prefixed env names;
root-caused in the issue's first comment, fix not confirmed landed. Q2: what should hard-block import
vs. stay advisory, including whether a large Flesch-Kincaid delta blocks. Q3: audit each stage's
`fail_safe` direction so a `verdict_parse_failed` cannot silently PASS what should have been flagged.
Q4: importer observability, a per-story anomaly summary, and a possible `--strict` mode). These surface
inside this exact runbook and currently have no other owner; treat them as in-scope, not backlog noise.

**Change.** This is an operational runbook plus small gap-filling, not a feature build:

1. Verify current database state first: query for `Storybook` rows owned by `CATALOG_FAMILY_ID`, their
   status, and their version. Do not assume the 2026-07-21 run's rows are still present or unmodified;
   this brief has no database access and cannot confirm that for you.
2. Run `import_catalog` against the target database regardless of step 1's findings; it is idempotent,
   so already-present rows come back `skipped_existing` and only genuine gaps (new files, prior
   `error`/`gate_blocked` entries) get written. Capture the report and reconcile it against step 1.
3. Address issue #347's open questions as part of this runbook, since they surface here: confirm the
   Q1 env-alias fix landed before trusting a fresh run's `in_review` verdicts; decide and document Q2's
   gating policy; complete Q3's fail-safe direction audit before treating step 4's sweep verdicts as
   trustworthy; add Q4's anomaly summary (and optionally `--strict`) to the importer if not already
   present.
4. Run the #529 re-moderation sweep over the full set (re-run entries included); triage FLAGs to the
   owner queue.
5. Owner executes gate G1 (publish list); promote approved books via `promote_catalog_story`.
6. Fix anything else the runbook surfaces (expected: little beyond #347; the tooling is otherwise
   tested).
7. Write the runbook as `docs/runbooks/catalog-import-publish.md`, with the DB-state check and #347's
   questions as named steps, so the next batch is turnkey.

**Tests/verification.** Post-publish: an integration test (or recorded manual pass) showing a kid
profile's `/v1/library` response contains catalog-visibility books in every offered band that has
approved content; UW-G14 flipped with Ref.

**Size S (process) + owner review time. Depends: nothing. Gate G1.**

### SQ-02: Fill-feasibility predicate in selection

**Status quo.** The automated fill is a single completion capped by
`generation/orchestrator.py::_MAX_TOKENS_PROSE = 32000` (used at the `_run_one_stage` call, line
~708). Selection (`generation/skeleton_match.py::select_skeleton_for_cell`) has no feasibility input;
a request landing on an oversized skeleton burns ~4 repair rounds and fails deterministically
(AL-046: 13 of 26 committed fills already exceed the cap).

**Change.**

1. New pure function `generation/feasibility.py::estimate_fill_tokens(skeleton) -> int`: sum of FILL
   `words=` targets converted to tokens (calibrate the words-to-tokens factor by regressing the
   committed fills in `out/`, 25 files: 23 top-level plus 2 pilot re-themes, against their actual
   token counts; commit the factor with its derivation as a module constant carrying a paired `#ASSUME`/`#VERIFY`: the `#ASSUME` states the factor, the `#VERIFY` names the committed regression evidence it came from)
   plus measured JSON scaffolding overhead per node. The infeasible-set size is factor-sensitive
   (plausible uncalibrated estimates give 16-29 of 58), which is exactly why the calibration comes
   first.
2. `candidates_for_cell` gains an optional `max_fill_tokens` filter (default from settings, wired to
   `_MAX_TOKENS_PROSE`); infeasible candidates are excluded on the automated path only (admin
   override and the skill path are unaffected: the skill authors interactively across many model
   turns and is not subject to the one-shot output cap).
3. Empty-after-filter cells raise the existing 422 with a new distinct reason string so the guardian
   surface can say "this length is temporarily unavailable" rather than a generic failure.
4. Log the feasible-pool size per request (structured, no premise text).

**Tests.** Unit: estimator against 3 committed fills within a stated tolerance; filter excludes a
known-oversized skeleton; distinct 422 reason. Regression: cells that were feasible stay feasible.

**Size S-M. Depends: nothing. Unblocked immediately.** Note: when SQ-03 lands, the predicate's cap
input changes from one-shot to per-chunk; keep the cap a parameter, not a constant.

### SQ-03: Act-scoped fill loop

**Status quo.** `generation/orchestrator.py::fill_skeleton` renders the whole storybook in one
completion (`_run_one_stage`), which caps renderable skeletons (16-29 of 58 infeasible, method-dependent; see SQ-02) and gives late
nodes degraded prose. AL-046 proposed act-scoped chunking and is the load-bearing precedent for this
brief. Correction from PR review: the skill path is NOT an existence proof of chunked filling; its
SKILL.md step 4 explicitly instructs a single-pass fill with a stable cached preamble. No chunked
fill exists anywhere today; this brief creates the first one.

**Change.**

1. Chunker: partition the node set into acts by graph structure (dominator-tree segments or the
   act-hub boundaries the beats already imply; the walker in `diversity/` has the traversal
   utilities). Scene closure is an enforced invariant, not a preference: nodes sharing a scene (a
   flowed single-choice run plus its terminal decision, per ADR-026 stop composition) must land in
   one chunk, so the chunk boundary search operates over scene units, not raw nodes. A single scene
   whose estimated tokens exceed the per-chunk cap is NOT silently split: the chunker raises a
   distinct, actionable error naming the scene's node ids (an authoring problem, not a runtime one;
   no production skeleton currently contains such a scene, and the error keeps it that way). Tests
   must cover exactly this case with a synthetic oversized scene.
2. Per-chunk prompt: shared stable system block (unchanged, cache-friendly) + prior-chunk summaries
   (titles and one-line outcomes only, not full prose) + this chunk's nodes. The differentiation
   directive and variation axis are restated per chunk (this is what makes SQ-05(b) uniform).
3. Stage-1 fidelity and word-count checks run per chunk; the repair budget is shared across chunks.
4. Reassembly asserts `skeleton.has_unfilled_directives(...) is False` and runs the existing
   whole-book gate unchanged.
5. Route-awareness handover (the SQ-02 interplay, made explicit after PR review): landing this brief
   flips the SQ-02 selector's feasibility input from the whole-story cap to the per-chunk cap, so
   previously infeasible skeletons re-enter automated selection; the estimator is retained for chunk
   sizing and pool logging. An end-to-end test covers candidate selection of a previously infeasible
   skeleton through its successful act-scoped fill.

**Tests.** Unit: chunker respects token cap and covers every node exactly once, on the largest
production skeleton (`the-tenfold-siege`, 677 nodes). Integration (mock provider): a previously
infeasible skeleton fills end to end; fidelity violations in chunk N do not re-render chunk N-1.
Live acceptance (owner-run, like the D4 pilot): one real fill of a previously infeasible skeleton,
recorded as a run record doc.

**Size M-L. Depends: SQ-02 (estimator). This is the deepest Stage 0 item; start it early.**

### SQ-04: Skill-path parity

**Status quo.** `story_requests/authoring_plan.py` persists differentiation metadata and a variation
axis for every job (`select_axis(str(request.id))` at line ~610), but only
`generation/worker.py::_differentiation_directive` reads it. `.claude/skills/cyo-author/SKILL.md` and
`generation/import_story.py` never consume it, so skill-authored fills (which produced the entire
current inventory) bypass every lever.

**Change.**

1. `import_story.py`: read the persisted `authoring_metadata` keys (`differentiation_level`,
   `prior_titles`, `prior_theme_tags`, `variation_axis`) when resuming a skill job and record them in
   the import report so the human author sees them.
2. `SKILL.md`: add a step that surfaces the rendered differentiation directive
   (`generation/prompts.py::build_differentiation_directive`) and the axis instruction
   (`generation/variation.py`) into the authoring context before the fill begins, with the same
   trusted-block placement rule the worker uses (outside the `UNTRUSTED_USER_INPUT` fence).
3. Parity test, semantic rather than textual: extract the worker's context assembly into (or wrap
   it with) a shared helper both paths call, then assert structurally in a fixture that (a) the
   differentiation directive and axis VALUES match between the worker-built and skill-instructed
   contexts, (b) both trusted blocks sit outside the `UNTRUSTED_USER_INPUT` fence, and (c) the
   required block ordering is preserved. A grep-level check cannot prove any of these three
   properties and is not sufficient; this is a safety-fence test, not a drift detector.

**Tests.** As above; plus the compliance-report template gains an "axis applied" field.

**Size S-M. Depends: nothing.**

### SQ-05: Wiring fixes (axis exclusion, repair context)

**Status quo.** (a) `generation/variation.py::select_axis(request_id, exclude=...)` supports
excluding recently used axes, but the sole call site (`authoring_plan.py` line ~610) passes no
exclude list and seeds by request id, so a guardian re-run reproduces the same axis on the same
beats. (b) The three repair surfaces rebuild prompts without the differentiation directive or axis:
structural repair (`generation/prompts.py`, `repair.md`), fidelity repair
(`generation/templates/fidelity_repair.md`), moderation soft-gate repair (`moderation/repair.py`).

**Change.** (a) Load the family's last N (propose 3) axis keys from `authoring_metadata` history and
pass as `exclude=`; seed by generation-job id, not request id, so re-runs draw fresh. (b) Append the
same trusted directive/axis block the fill used to each repair prompt; the block is already PII-safe
by construction (titles and closed-vocabulary tags only).

**Tests.** (a) Re-run of the same request draws a different axis (seeded test); consecutive family
requests avoid the last 3 axes. (b) Prompt-fixture tests: each repair template contains the
directive block when metadata is present; absent-metadata path unchanged.

**Size S. Depends: nothing. Do this first; it is the plan's cheapest real gain.**

### SQ-06: Cover-art style variation

**Status quo.** `covers/prompt.py` (style clause at lines ~107-110) applies one fixed clause to every
book: "warm, whimsical, hand-illustrated children's book art...". Only the safety clause varies.

**Change.** A small style table keyed by `(band, tone)` (tone from `story_requests/tone.py`'s closed
vocabulary): propose 4-6 clauses (picture-book warm for 3-5/5-8; adventurous ink-and-wash for
8-11/10-13; moodier painted styles for teen prose; stark graphic style for gamebooks). Safety clause
logic untouched. Deterministic selection (band+tone, not random) so re-generation is stable.

**Tests.** Unit: each band maps to its clause; safety clause always present; snapshot of the built
prompt per band.

**Size S. Depends: nothing.**

---

## Stage 1 briefs

### SQ-07: Selection rebalance

**Status quo.** `generation/skeleton_match.py`: `_weight = 1/(1+recent)` (recency),
`_blended_weight = 1/(1+recent+3*similar)` (`_THEME_REUSE_PENALTY = 3`), then a multiplicative theme
attraction `weight *= (1 + theme_overlap)` up to 2x (`_theme_overlap_bonus`,
`theme_overlap_for_candidates`). History is family-scoped: `recent_skeleton_usage` counts the last 20
`storybook_version` rows (`_RECENT_WINDOW = 20`), all statuses, versions counted separately.
`diversity/history.py::load_family_history` mirrors the window. No `profile_id` exists in
`diversity/`. `structure_features` is computed and unused by selection.

**Change**, in four separable commits, lettered (a)-(d) to match the plan's references:
(a) **Cap the attraction bonus** (gate G2, default 1.3x): change the multiplier to
   `(1 + min(theme_overlap, CAP - 1))`, constant with rationale; add the cross-family Monte Carlo
   from the plan's acceptance as a committed simulation test.
(b) **Per-profile scoping**: add optional `profile_id` to `load_family_history` /
   `recent_skeleton_usage` (the storybook row already carries the requesting profile through the
   request join; verify the join path in `db/models.py` and document it); selection prefers
   per-profile counts, falls back to family when the profile has fewer than K (propose 5) rows.
   Paired `#ASSUME: data-integrity`/`#VERIFY` on the fallback (the `#VERIFY` points at the join-path test that proves per-profile rows resolve). Privacy: internal-use only, no new surface;
   confirm classification per the plan's risk note before merging.
(c) **Distinct-storybook counting**: count distinct `storybook_id`, not version rows, in the recency
   window (kills the retry-pollution loop); keep the window at 20 storybooks.
(d) **Structural de-weighting**: extend `_blended_weight` with a proximity term: for each candidate,
   `sim = max over reader's last M trees of (1 - structural_distance)`; fold in as
   `1/(1+recent+3*similar+w_s*sim)` with `w_s` starting at 1 (documented, re-derivable). When SQ-15
   lands, the distance input switches to the experience-metric distance; keep the term's input a
   callable for that swap.

**Tests.** Existing selection tests must pass untouched where behavior is unchanged; new: cap
simulation (concentration toward 1/3), per-profile preference and fallback, distinct-storybook
window, structural term never zeroes a weight (C-4 pinned).

**Size M. Depends: nothing (A1-A5 delivered). Gate G2 for the cap value only; land 2-4 regardless.**

### SQ-08: Flywheel trigger respec

**Status quo.** `flywheel/trigger.py`: a cell triggers on >= `DEFAULT_MIN_CATALOG_EVENTS = 3` CATALOG
escalations from >= `DEFAULT_MIN_DISTINCT_REQUESTS = 2` distinct `request_id`s. Upstream,
`diversity/query.py::score_history` only reaches CATALOG when every cell slug has a similar-theme
story in the window and one has two; an empty/unknown theme signature scores similar to nothing, so
out-of-vocabulary themes never escalate (analysis section 5, dark sensor).

**Change.**

1. `trigger.py`: count distinct *families* with `DEFAULT_MIN_DISTINCT_FAMILIES = 2`. Contract
   decision, stated so the enum-only payload rule survives: the `CELL_SATURATED` payload today
   carries only `age_band`/`length`/`style`/`level`, and the trigger counts distinct request
   anchors from `entity_id`. Family scope reaches the trigger via a **request-to-family join at
   read time** (the event's `entity_id` is the request id; join to the request row's `family_id`
   when scanning), NOT by adding `family_id` to the event payload, which would put an identifier in
   a payload that is deliberately closed-enum-only. The trigger's reader half re-validates as today
   and drops rows whose request no longer resolves. An end-to-end test covers emission through
   distinct-family counting, including two requests from one family collapsing to one.
2. `query.py`: unknown-signature conservatism. An empty request signature currently returns
   containment 0.0 everywhere (correct for the WS-0 "never registers as similar" intent on the
   *guard* side, wrong on the *saturation* side). Split the read: saturation accounting treats an
   empty-signature request as matching every candidate slug at a discounted weight (propose 0.5), so
   repeated unknown-theme requests still saturate a small cell; the neighbor list and ATG pairing
   keep the existing conservative-empty behavior. Document both sides where they diverge.
3. Simulation test module: multi-child window churn scenario reaches CATALOG within a stated number
   of similar requests; single prolific family alone does not trigger.

**Size S-M. Depends: nothing. Blocks SQ-20/SQ-23.**

### SQ-09: Clone labeling and A9 resolution

**Status quo.** `diversity/incell.py` audits in-cell pairs against `TAU_CELL` from
`docs/planning/ws5_floor_baseline.json`; `ALLOWLIST` holds exactly the
`the-harrowstone-keep`/`the-sunken-temple` pair (graph-isomorphic; measured distance 0.000469 in `ws5_floor_baseline.json`, while an earlier doc and the incell docstring carry 0.00095: either way about two orders under the floor, and the discrepancy is worth fixing in passing); stale allowlist
entries fail the gate, so the list can only shrink. A9 item 2 (restructure book 2 past the floor,
including the 35-ending remix, 5 variables, 20 conditions, 75 effects) is specified in UW-G03.

**Change.** (a) Add `weisfeiler_lehman_graph_hash` comparison (within-run only; networkx >= 3.5
changed directed hashes, so never persist hashes) to the audit's report line: label breaching pairs
ISOMORPHIC vs NEAR. Size S. (b) Execute the UW-G03 restructure as an authoring task: this is a
content change to a series book, so `SR-9` (series continuity) must pass with book 1's carried
states, and the ending remix must hold PL-15/16/17/24. Follow the cyo-author skill (with SQ-04
parity landed). Size L; the one Stage 1 item that is authoring, not code.

**Tests.** (a) unit with a renamed-clone fixture. (b) full gate + `validate_series` green on the
brass-lantern chain; in-cell audit passes with an empty allowlist.

**Depends: (b) benefits from SQ-04. Pairs with SQ-21's outcome-economy work on the same books.**

### SQ-10: Metrics honesty

**Status quo.** `diversity/aggregate.py`: `effective_catalog_size` (entropy over slugs),
`repeat_adventure_rate` (PS >= 0.70 over a family window); both explicitly never gate. The flywheel
reports net new trees per month. Analysis section 5: ECS is maximized by uniform rotation; RAR is
family-windowed; net-new-trees counts TAU_CELL-distinct merges.

**Change.** (1) New report in the WS-0 harness: per-theme-cohort concentration, defined exactly so
two implementations cannot diverge. For each canonical tag `t` in the similarity vocabulary: the
cohort is the set of families having at least one request whose `similarity_signature` contains `t`;
each family contributes exactly its FIRST such request (by `created_at`); the denominator `N_t` is
the cohort size; the share is `max over slugs s of (families whose contributed request drew s) /
N_t`. A request whose signature contains multiple tags contributes to each tag's cohort. Cohorts
with `N_t` below a privacy floor (propose 3) are suppressed from the report, listed only as
suppressed. Ties for the modal slug are not broken arbitrarily: all tied slugs are reported with a
tie flag. Tags with an empty cohort report `N_t = 0`, no share. No premise text anywhere, tags and
slugs only. The unit-test fixture covers a multi-tag request, a tied mode, an empty cohort, and the
suppression floor. (2) Docstring caveats on ECS/RAR/net-new-trees stating what
each cannot see, with a pointer to analysis section 5 (docstrings are load-bearing here; the WS-0
report template prints them). (3) When SQ-15 lands: add experience-weighted ECS (entropy over
experience-metric clusters instead of slugs) beside, not replacing, slug ECS.

**Tests.** Report unit test with a synthetic concentrated population; template snapshot.

**Size S-M. Depends: (3) on SQ-15.**

---

## Stage 2 briefs

### SQ-11: Alternate-beats ADR

**Status quo.** Beats are single frozen strings inside `<<FILL role=R words=N beats='...'>>`
(`storybook/slotted_surfaces.py::FILL_DIRECTIVE_RE`); `generation/binding.py` substitutes slots into
them under four post-conditions (fingerprint unchanged, CR-1 role/words map preserved, no residual
tokens, gate not blocked); the fidelity review targets the beat text.

**Design questions the ADR must answer** (with proposed defaults):

1. **Storage**: variants live beside the primary beat. Proposal: extend the directive grammar to
   `beats='...' alt1='...' alt2='...'` OR a sidecar `<slug>.variants.json` keyed by node id. Prefer
   the sidecar: the directive regex, `structure_fingerprint`'s strip logic, binding's
   reconstruction, and every existing parser stay byte-compatible. Wiring the sidecar in is real
   work the ADR must spec, not a free ride: `SIDECAR_SUFFIXES` in `generation/skeleton.py` lists
   only `.contract.json` and `.lineage.json`, so `.variants.json` must be added to `is_sidecar()`
   or catalog scans will load it as a skeleton; `import_catalog`/`import_story` and promotion copy
   only the filled blob today, so the issued variant set (or its selection key) must be persisted
   with the published version for reproducibility; and `render_bound_skeleton` must substitute
   slots into the issued variant during reconstruction. A round-trip test proves the selected
   variant's text appears in the filled output while the fingerprint is unchanged (variants are
   leaf content; the fingerprint must NOT change when variants are added).
2. **Outcome contract**: a variant must preserve the node's successor set, choice semantics, ending
   kind/valence, and any effect/condition semantics. The contract is checked structurally for free
   (variants cannot touch graph fields, only the beat string) plus a human review rule for semantic
   drift.
3. **Selection**: deterministic per fill, seeded by generation-job id (blake2b, same pattern as
   `variation.py`), choosing one variant *set* per fill (all nodes from the same variant index where
   present, falling back to primary), so a fill is coherent rather than a per-node shuffle.
4. **Fidelity target**: `render_bound_skeleton` substitutes slots into the *issued* variant; the
   Stage-1 review and CR-1 map check run against it unchanged.
5. **Authoring policy**: variants per node authored under at least two distinct model/prompt
   configurations (anti-monoculture, analysis 2.7); ending nodes and climaxes first (highest
   perceived-repeat load), corridors last.
6. **Slot interaction**: variants must use the same slot tokens as the primary beat (the contract's
   slot set is per node); `scripts/check_theme_contract.py` extends to validate variants.

**Deliverable**: the ADR + schema/validation code for the chosen storage + the
`check_theme_contract.py` extension. **Size M. Gate G3.**

### SQ-12: Beat-variant pilot

**Status quo.** `the-lost-mitten` (11 nodes) and `the-clocktower-cipher` (25 nodes) are the two
A20-complete skeletons with passing contracts; the D4 pilot run record
([d4-pilot-run-20260731.md](d4-pilot-run-20260731.md)) is the template for committed live-run
evidence.

**Change.** Author 2-3 variants per node for both skeletons under SQ-11's rules (two authoring
configurations for the VARIANT AUTHORING; the generation arms below hold everything else fixed).
Pre-register the experiment in the run record BEFORE generating, including the controls that isolate
the variant effect: both arms use the identical provider, model, prompt template, exemplar
configuration, and where the provider supports it, generation seed; the analysis sample (number of
pairs, pairing rule) is fixed in advance. Arms: (i) paired fills on the same skeleton and theme with
the SAME variant set, (ii) with DIFFERENT variant sets; arm (i) is the provider-noise baseline, so
the measured effect is (ii) minus (i), not (ii) alone. Pre-registered decision rule: median masked
`d_uni` for (ii) exceeds (i) by >= 0.10 on >= 6 fill pairs per skeleton, evaluated as a paired
comparison per pair (report the per-pair deltas, not only the medians); RL-13 non-regression means
no fill in either arm moves outside its band's reading-level envelope, checked with the existing
RL-13 gate before any distance analysis. Record hours spent per node (feeds the capacity model).
Commit the report; the margin met or the program-stop decision recorded either way.

**Size M. Depends: SQ-11. Gate: none (G3 already accepted the ADR); the pilot IS the gate for
SQ-13/SQ-14.**

### SQ-13: Combined A20 + variants rollout

**Status quo.** 14 skeletons / 4,305 FILL nodes unslotted (UW-G01, distribution extremely uneven:
677/550/550 at the top; the smallest UNSLOTTED skeletons are 105 and 32 nodes; the 25- and 11-node MVP seeds are the two already-delivered A20 slices, not backlog); 47 contracts exist. Scope correction from PR review: the rollout covers the 58 production-eligible skeletons, not only the unslotted set; the 13 unslotted PRODUCTION skeletons get the combined pass (the 14th no-contract file is the MVP seed `the-sunken-signal`, excluded with the test-tier scaffolds), the 45 production already-contracted skeletons get a variants-only pass, and every per-skeleton pass backfills subject-axis values into the skeleton's existing `metadata.themes` list (a real field on all 61 skeletons; the 9-of-22 gap is subject VALUES missing from it, not a missing field). The A20 toolchain is proven:
`scripts/parameterize_skeleton.py` applies a slotting plan with fingerprint unchanged;
`scripts/check_theme_contract.py` runs seven acceptance checks; two authoring conventions are
recorded in plan v2's A20 correction (article inside the slot value, never sentence-initial; whole
ending titles as `*_TITLE` slots).

**Change.** Per skeleton, one pass: slotting plan -> `parameterize_skeleton.py` -> variants under
SQ-11 -> `check_theme_contract.py` (extended) -> PR. Ordering: (1) most-requested cells from serving
data once SQ-01 ships (fallback order until then: kid bands smallest-first); (2) the 300+ node teen
books last and only after SQ-03. Maintain the rollout tracker table appended to the plan; every
flywheel promotion (SQ-20/SQ-23) appends its slice here at merge time (capacity rule).

**Size L (program; per-skeleton slices are S to L individually). Depends: SQ-11, SQ-12; large trees
on SQ-03.**

### SQ-14: ATG calibration and blocking

**Status quo.** `diversity/leaf.py`: `_BAND_THRESHOLDS = {}` (every band uses the uncalibrated
section-3.2 defaults: fail_median 0.40, fail_p25 0.30, pass 0.60/0.45);
`diversity/query.py::select_atg_comparison_partner` returns only the most recent same-tree fill;
`moderation/leaf_diversity.py` is advisory and fail-open **by supervisor-ruled contract** (module
docstring), with five silent no-op paths (no slug, no partner, missing blob, invalid blob,
fingerprint drift). Findings ride the one bounded repair in `moderation/repair.py`.

**Change**, strictly after SQ-12's margin is met:

1. Calibrate `_BAND_THRESHOLDS` per band from the pilot's paired-fill distributions (the pilot gives
   both a "genuinely different" and a "same-variant" distribution per band it covers; extend the
   panel to uncovered bands with the SQ-13 rollout's first fills).
2. Partner selection: k=3 most recent same-tree fills, minimum distance is the verdict input;
   per-profile scope with family fallback (shares SQ-07(b)'s history plumbing).
3. Contract revision (gate G4): FAIL becomes blocking on the automated path with the bounded repair
   as remediation and `needs_review` (human) as the terminal fallback; every fail-open path is
   enumerated in the module docstring and either justified (fresh_generation has no partner: stays
   open) or closed (missing blob: becomes a logged retryable error).

**Tests.** A deliberately templated fill (noun-swap fixture) FAILs and blocks; a variant-differing
fill PASSes; each fail-open path has an explicit test asserting its documented behavior.

**Size M. Depends: SQ-12 (hard); SQ-07(b) (plumbing); per-skeleton blocking additionally gated on that skeleton's SQ-13 slice, with global blocking only after SQ-13 covers the production cells (see plan section 1.1). Gate G4.**

---

## Stage 3 briefs

### SQ-15: Per-path experience metrics

**Status quo.** `diversity/structure.py::structure_features` computes 11 numeric features plus
histograms; none is path-scoped. The plan-v2 measurement pass built a walker validated in lockstep
against `StoryEngine` (0 divergences / 1,800 walks); ADR-026's `player/stops.py::compose_stop`
defines the rendered-stop unit for 8-11+.

**Change.** New module `diversity/experience.py` (pure, no I/O, same import rules as the package):

- `decision_cadence`: real choices per 1,000 words over N seeded uniform walks, computed over
  rendered stops for flowed bands (reuse `compose_stop`) and raw nodes for 3-5/5-8.
- `corridor_ratio`: fraction of stops/nodes with exactly one choice on the sampled walks.
- `outcome_entropy`: Shannon entropy of ending (kind, valence) over the walk sample.
- `median_walk_depth`: median stop-count to an ending over the sample (AL-027's statistic).
- `agency_density`: share of decision stops whose options reach different ending valences.
Deterministic seeding (no `random` without a seed; follow `variation.py`'s blake2b pattern).
Commit the 61-skeleton baseline as a JSON report under `docs/planning/evidence/`. Wire: SQ-07(4)'s
proximity callable and `flywheel/strategy.py::ranking_key` consume a weighted experience distance.

**Tests.** Lockstep property pinned (walker vs engine on the conformance corpus); metric unit tests
on hand-built graphs with known values; baseline regeneration is deterministic.

**Size M. Depends: nothing (walker exists). Feeds SQ-07(4), SQ-10(3), SQ-16, SQ-20.**

### SQ-16: Stop-based section 10 compliance measurement

**Status quo.** ADR-011 section 10 defines cadence over rendered stops; nothing in the validator
computes stop adjacency (UW-C23); `validator/choice_grammar.py` CG-1..CG-4 are inert in production
(`enforce_grammar=False` everywhere, UW-C24) and CG-1 is a node-level backstop, not the rule.

**Change.** Report-first: a script (`scripts/measure_choice_grammar.py`) that composes stops via the
shared conformance logic and measures each skeleton against the section 10 table (choice cadence,
max choiceless stops in a row, options per choice, words per stop). Output a per-skeleton compliance
table committed under `docs/planning/evidence/`. NO gating change in this brief; the gating decision
(flip `enforce_grammar` for new skeletons per D3/D11) is recorded separately with the measurement
attached, honoring the AL-051 rule (a rule firing on 100% of a class is a misunderstanding).

**Size M. Depends: SQ-15 (shares stop composition). Informs SQ-17.**

### SQ-17: D11 replacement floor

**Status quo.** Design-review decision D11: once one grammar-compliant skeleton exists in a cell,
grandfathered skeletons are excluded from selection there. At the flywheel's 4-merges/month rate this
schedules pool-of-1 cells (analysis section 5).

**Change.** Amend D11 in [design-review-kid-appeal-2026-08-01.md](design-review-kid-appeal-2026-08-01.md)
(one paragraph, owner sign-off) to: exclusion begins when >= 2 compliant trees exist in the cell.
Implement the filter in `skeleton_match.skeleton_matches_cell` behind the D11 `deprecated` marker
mechanism when that lands (W2.4); until then this is a documented rule with a simulation test
asserting no transition state yields a feasible pool below 2.

**Size S. Depends: conceptually on SQ-16's existence, not its results.**

### SQ-18: A13b + engagement rollup

**Status quo.** A13b ("Try a different way" at the ending screen: walk up to 3 hops to the last real
pick, fall back one step, availability exactly today's `path.length > 1`) is fully specified in
[story-diversity-plan-v2.md](story-diversity-plan-v2.md) row A13b and authorized by ADR-024; not
built. Engagement telemetry is **designed but not built**: `node_engagement` is a table proposed in
[reader-path-engagement-design.md](reader-path-engagement-design.md) (`status: proposed`) and has
zero occurrences in `src/` or `supabase/migrations/`. As designed it keys per
`(storybook_id, version, node_id)` with no skeleton rollup, which is the gap (b) closes; but there is
no deployed telemetry to roll up until that design is ratified and shipped.

**Change.** (a) Implement A13b in `frontend/src/player/` + `Reader.tsx` per the A13b row's exact
semantics (the row text is the spec; respect its two MUST NOTs: availability must not become
"untaken choice exists within 3 hops", and the walk stops at the first branching ancestor). Apply
A18's glyph differentiation while in the file. (b) Backend, **conditional on the telemetry existing**:
ratify and ship reader-path-engagement-design.md (its own decision, not assumed by this brief), then
add a rollup query/view joining `storybook_version.skeleton_slug` so per-stop signals aggregate
across fills of a tree; expose in the WS-0 report, not a new API. If the design is not ratified, (b)
does not start and the brief closes on (a) alone. If any API shape changes: regenerate the frontend
client (0.3).

**Tests.** Frontend: the preserved-climax case (take A, die, go back, take B, win) keeps the button
visible; 3-hop and fallback cases from the plan-v2 measured terminals. Backend: rollup unit test.

**Size M. Depends: (a) nothing; (b) hard on reader-path-engagement-design.md being ratified and its
`node_engagement` table shipped (neither is scheduled by this plan, so (b) may not become
actionable). Frontend + backend pair; (a) is the good parallel item for a second engineer.**

### SQ-19: Path-length honesty

**Status quo.** PL-20 floors only the fastest satisfying path; nothing constrains typical read
length (AL-027, open); PL-17's gamebook endings floor (25% of nodes) rewards terminating-leaf
breadth (AL-026 lesson; reshape tracked as UW-M06).

**Change.** (a) AL-027's advisory: median-uniform-walk stop count per cell (SQ-15's
`median_walk_depth`) with a WARNING below a per-cell floor derived from the cell's whole-world
minutes; advisory only, calibrated from the SQ-15 baseline. (b) UW-M06: propose the PL-17 reshape
(e.g. count only endings at >= X% of `min_complete` depth toward the floor, X calibrated so no
current skeleton flips class: run the impact report first, AL-051). Both land as validator changes
with catalog impact reports committed.

**Size M. Depends: SQ-15. Validator changes in service of authoring: lessons-log rule applies.**

---

## Stage 4 briefs

### SQ-20: Targeted flywheel run

**Status quo.** `flywheel/strategy.py` has four chain templates (T1: M3 graft + M2 re-map; T2: M1 +
M2; T3: M4 insert-decision + M1 + M2; T4: M5, Tier-2), caps (12 attempts/cell, 3 open PRs, 30-day
cooldown, 4 merges/month), and a ranking key on structural distances. Zero promotions ever. AL-049:
M3/M4 operators fail or time out on state-heavy ceiling-size books.

**Change.** Operator smoke-test first: run T1-T3 against every Tier-1 cell's parents offline
(`scripts/mutate_skeleton.py`), record which cells have viable parents; pick one 3-tree Tier-1 cell
with headroom (avoid AL-049's profile). Drive one candidate through: chain -> reguide (resolve every
`ReguideItem` by hand-authoring the invalidated beats) -> acceptance stages -> `.lineage.json` ->
promotion PR -> owner review -> merge. Attach the SQ-15 experience-distance report to the PR (the
merge decision cites it, not only TAU_CELL). Record hours (capacity model). Then fix or explicitly
scope out AL-049 (register row update either way).

**Size M-L. Depends: SQ-08 (sensor honesty), SQ-15 (judgment), SQ-13 capacity rule (the merged tree
immediately queues its slotting+variant slice).**

### SQ-21: Outcome-economy spread

**Status quo.** Analysis 2.2: four of six gauntlets share the identical 2-positive/1-neutral ending
signature; gamebook cells have near-zero outcome-mix variance; the fail-kind mix keys satisfying-path
mass (eta-squared 0.636). ADR-011 sanctions "few wins, many fails" without numbers.

**Change.** Authoring program, one gamebook cell at a time (start 13-16/long, which pairs with
SQ-09(b)'s restructure): re-map endings via the M2 operator where possible (it exists precisely for
valence-class-preserving remixes; note its self-declared metric blindness means judgment is by SQ-15
outcome entropy, not structural distance) and hand-edit where the target mix crosses valence classes
(then it is an authoring change through the full gate). Acceptance is measured, not eyeballed
(tightened after PR review): before remixing a cell, pre-register in that cell's authoring plan the
per-tree target table (win count, ending-kind histogram, setback:death:capture ratio) and a floor on
the minimum pairwise outcome-mix distance between the cell's trees (L1 over the normalized
ending-kind histogram, computed by SQ-15's `outcome_entropy` module; the floor is set against the
current catalog's measured near-zero baseline and committed with the plan). Evidence is a committed
per-cell report of actual vs target per-tree counts plus the pairwise distances. PL-15/16/24 remain
validity rails, not the diversity proof.

**Size M-L per cell. Depends: SQ-15 (judge), pairs with SQ-09(b).**

### SQ-22: Pathfinder Phase 0 decision

No implementation until gate G5. The decision package is already written
([pathfinder-structure-exploration.md](pathfinder-structure-exploration.md) section 8); the team's
only task is to keep it out of scope until the owner and legal gates clear. If go: Stage 1 pilot per
that document, one 13-16 gamebook skeleton, unchanged validator.

### SQ-23: Demand-driven expansion

No implementation until the SQ-08 sensor flags a cell post-launch. When it does: Wave-5-style design
(deliberately varied designer configurations per SQ-11's anti-monoculture policy), judged by SQ-15,
scheduled under the capacity rule. Each expansion PR cites its triggering saturation evidence.

## Cross-cutting brief

### SQ-24: ADR-011 amendment

**Change.** One amendment PR to `docs/planning/adr/adr-011-story-scale-framework.md`: replace the
"JHM 2019" shorthand with the full citation (Adams, Beckelhymer and Marr 2019, DOI
10.5642/jhummath.201902.05, [research/cyoa-structure-measurements.md](research/cyoa-structure-measurements.md));
mark decisions-per-playthrough as derived (~5-6 typical, ~8 longest); label words/node and
total-words as designer priors and split total-vs-playthrough words; add the Ashwell
eight-pattern-to-six-topology mapping table; resolve the five UW-G17 reconciliation actions
(reconvergence targets may resolve to "keep `reconvergence_ceiling` unset, monitored via SQ-15",
which is a legitimate outcome). Closes UW-C25 and part of UW-G17 with Refs; AL-079 flips to applied.

**Size S-M. Depends: research/ (done). Gate G6.**
