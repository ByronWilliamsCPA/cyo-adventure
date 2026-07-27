---
title: "Handoff: Authoring Lessons Log and Story-Quality Gates (PR #416)"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Transfer PR #416 and its withheld story artifacts to the local team, including the rebase work the merged diversity and personalization PRs now require."
tags:
  - planning
  - handoff
  - validation
  - authoring
component: Development-Tools
source: "session 7641f257, 2026-07-25 to 2026-07-27"
---

# Handoff: Authoring Lessons Log and Story-Quality Gates

> **Date**: 2026-07-27 | **PR**: [#416](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/416)
> **Branches**: `claude/story-process-tooling-mqr9zy` (the PR) and
> `claude/dnd-story-game-series-mqr9zy` (the withheld stories)
> **Verified against**: `main` at `85de102` (v0.37.0), after PRs #413, #415, #417, #418 merged

## 1. What this is

Two deliverables came out of one session that built a three-book 16+ gamebook series at the
ADR-011 node ceiling (746 nodes) and then treated the build as a load test of the authoring path:

1. **PR #416, the process and tooling work.** Pushed, green, and reviewable now.
2. **The story artifacts themselves**, deliberately held back on a second branch for a later push.

Everything in section 4 is work the merged PRs make **necessary**, not optional: PR #416 currently
has **7 merge conflicts** against `main` and two outright duplications. Section 5 is the story push,
which has one **blocking** problem.

Read section 3 first if you are picking this up cold. Read section 4 before touching the PR.

## 2. State of each branch

| | `claude/story-process-tooling-mqr9zy` (PR #416) | `claude/dnd-story-game-series-mqr9zy` |
| --- | --- | --- |
| Contents | validator rules, tooling, tests, process docs | the three books plus their derived artifacts |
| Base | `origin/main` at `79e10c5` (now 8 commits behind) | same lineage, full history of the build |
| Suite at push time | 4702 passed, 6 skipped, 3 xfailed, ruff clean | 4743 passed, 3 xfailed |
| Merges into current `main`? | **No, 7 conflicts** (section 4) | not attempted; needs section 5 |
| Safe to squash-merge as-is? | No | No |

The 6 skips on the PR branch are the story-dependent tests skipping **by design** (`pytest.skip`
when the artifacts are absent), not by accident. They activate when the stories land.

## 3. What the PR contains, in one pass

**The one item worth reviewing first.** `moderation/classifiers.py` called the bright-line
classifiers once per node in a loop guarded by `if key and reason is None`, so the **first**
`ClassifierUnavailable` disabled that classifier for **every remaining node**, and the only trace was
a non-gating `ADVISORY`. On a 746-node story that is 1,492 sequential third-party calls, which is the
shape that trips a Perspective ~1 QPS quota; a 429 partway through left most of the book unscreened
for `sexual/minors`, `self-harm/instructions` and `illicit/violent`, and both `submit()` and
`approve()` passed the result. It now retries with backoff, opens a circuit breaker rather than
hammering a down provider per node, tracks per-node coverage, and emits a **gating** FLAG naming the
shortfall. The single-item intake screen opts out (`report_coverage=False`) because intake is
documented fail-open with the guardian as the gate.

**New rules.** PL-23 (declared `estimated_minutes` vs the derived fastest-finish clock), PL-24
(ending-mix: single-kind ceiling plus a style-aware winnability floor), SR-8 (carried-variable
integrity across a chain). All advisory except SR-8's two data-loss cases.

**Author feedback.** L2-11 now names *why* a branch is dead. `check_skeleton --headroom` reports
proximity to every budget edge. RL-13 stops scoring `<<FILL>>` directives.

**Process.** `docs/planning/authoring-lessons-log.md`, 52 lessons (28 applied, 20 open), one row per
lesson with a mandatory proposed change, validated by `scripts/check_lessons_log.py` and mandated in
`CLAUDE.md` plus the `cyo-author` skill. **This log is the map for everything left to do**; sections
4 and 5 below are largely pointers into it.

**Found in existing content by the new advisories** (all advisory, nothing blocked): 13 of 23
committed fills declare a read time more than 25% from their derived clock; 6 books have one ending
kind above 60%, one at 98% `setback`; 3 committed fills cannot pass the gate at all.

## 4. Required changes from the merged PRs

Verified by dry-run merge and by running `main`'s code against these artifacts. Two duplications, one
composition, one version collision, four textual conflicts.

### 4.1 Delete the duplicate lockstep test

PR #415 shipped `tests/unit/test_validator_rules_catalog.py`, "the lockstep test the plan wrongly
assumed already existed". This PR independently added `tests/unit/test_rule_catalog_lockstep.py` for
the same purpose.

**Action**: delete ours, keep theirs. Before deleting, check two assertions of ours are covered by
theirs and port them if not: the guard-the-guard test (fail if the id scan finds fewer than 20 rules,
so a changed emission pattern cannot silently blind the check), and the fact that ours scans
`rule_id="..."` literals across all of `validator/` rather than an enumerated list.

### 4.2 Rebase the catalog rather than merging it

`docs/planning/validator-rules.md` conflicts, and both sides call themselves **v1.3**. `main`'s
version already documents L2-13, L2-14, SR-1..SR-7 and SR-9, and it carries an explicit reserved row:

> `| SR-8 | Series | **RESERVED, not implemented here.** Claimed by the open PR for the
> authoring-lessons workstream (#416). ... |`

That reservation is why there is **no rule-id collision**: #415 took SR-9 and L2-14 and left SR-8,
PL-23 and PL-24 alone.

**Action**: discard our catalog diff and re-apply only what is genuinely ours on top of `main`'s:
the PL-23 and PL-24 rows, and the SR-8 row **replacing** the RESERVED placeholder. Drop our SR-1..SR-7
section and our L2-13 row entirely; `main` has both, written independently. Bump to **v1.4**, not 1.3.

### 4.3 Compose the two `reading_level.py` changes, do not choose

PR #418 made RL-13 strip personalization sentinels before scoring, so grades are not skewed by
`{~SLOTID:GenericWord~}`. This PR made RL-13 skip unfilled `<<FILL>>` bodies. **Both are needed** and
they are independent. The composed order in `check_reading_level`:

1. skip the node entirely if the body contains `<<FILL` (a directive is not prose)
2. `strip_sentinels(body)` on what remains
3. apply the existing `_MIN_WORDS_FOR_FK` floor to the stripped text
4. score

Our regression test (`test_unfilled_skeleton_bodies_are_not_scored`) and theirs must both pass.

### 4.4 Keep SR-8 alongside SR-9, and say why in the docstring

`main`'s SR-9 validates that a book's *reachable satisfying exit states* leave the next book winnable.
Our SR-8 validates the *declarations*: receiving range must contain the sending range (ERROR),
matching type (ERROR), no silently dropped variable (WARNING). These overlap but neither subsumes the
other, and there is measured evidence that SR-8 still earns its place:

```text
$ validate_series([book1, book2, book3])   # on current main, no SR-8
SR chain ok: True  findings: 2
  SR-9 [warning] book 1 has more than 64 distinct satisfying exit states or capped its
                 walk, so the continuation handoff into 'sk_sunless_march' was checked
                 over a truncated sample
  SR-9 [warning] book 2 ... same, into 'sk_ninth_hand'
```

On a real chain SR-9 **truncates at 64 exit states and says so**. SR-8 is a declaration-level check
that cannot be defeated by walk truncation, and it is what would have caught the actual bug this
session shipped (book 3 declaring `renown [3,5]` after a book that ends anywhere in `[0,5]`, silently
clamping every low-reputation playthrough to the maximum).

**Action**: wire `_check_carried_variables` alongside SR-9, and note the truncation complementarity
in its docstring so a later reader does not delete it as redundant.

### 4.5 Textual conflicts, no design decision needed

- `src/cyo_adventure/validator/layer2.py`: our L2-11 cause hints vs their L2-14. Keep both.
- `tests/unit/test_layer2_validator.py`, `tests/unit/test_reading_level.py`,
  `tests/unit/test_series.py`: both sides appended cases. Keep both sides.
- `docs/planning/capability-register.md`: `main` is v1.8 (G18/K20 for ADR-023 personalization). Re-apply
  our A11, G9 and S12 notes on top and bump to v1.9.
- `api/node_edit.py` and `moderation/rescreen.py` **auto-merge cleanly**; no action.

### 4.6 Two log rows are now superseded by merged work

- **AL-014 / AL-044** (no anti-clone check reachable for a hand-authored skeleton) is **solved** by
  #415's `scripts/check_incell_clones.py`, a blocking CI gate with a self-pruning allowlist. Mark both
  rows `superseded` with that script as the `Ref`. Note their independent finding that the
  harrowstone/sunken-temple pair is a *re-skin* (shape copied, 1,326 of 1,503 slotted surfaces
  differ), which inverts the fix from "replace" to "restructure" and applies equally to our book 2.
- **AL-017** (catalog drift) is half theirs now; keep the row but point the `Ref` at both tests.

## 5. The story push, and its one blocker

Verified against `main` at `85de102` by copying the artifacts into a clean worktree:

| Check | Result |
| --- | --- |
| `run_story_gate` per book | 0 / 0 / 1 finding (the expected L2-13 scale advisory) |
| New L2-14 (no-way-out) | does not fire; no forbidden ending kinds at 16+ |
| `validate_series` incl. SR-9 | `ok: True`, 2 truncation warnings |
| **`check_incell_clones.py`** | **FAIL** |

```text
FAIL 0.00047  13-16/long/gamebook   the-harrowstone-keep vs the-sunken-temple   (pre-existing)
FAIL 0.01394  16+/medium/gamebook   the-sunless-march vs the-vault-of-nine-iron  (ours)
```

Book 2 was derived from book 1's topology deliberately, for series continuity. That decision now
fails a blocking gate at **0.01394 against `tau_cell` 0.05**, and it is the same defect class #415
scoped under "A9 item 2" with a measured target (5 vars / 20 conditions / 75 effects plus a 35-ending
remix for distance 0.0710). **This needs an owner decision before the stories can land**: restructure
book 2's graph, or add an explicit series-continuity allowlist entry. Note #415 rejected
topology-relabelling as metric-gaming, on the record, so that route is closed.

**Story-push checklist**, in order:

1. Resolve the clone-gate failure above.
2. Rebase the story branch onto current `main`.
3. **Re-render the diagrams on a machine with graphviz** (see 6.1). The three committed SVGs are
   invalid and must not ship.
4. Regenerate `docs/planning/ws5_floor_baseline.json` (`scripts/calibrate_mutation_floors.py`) and
   `docs/architecture/story-skeletons.md` plus the `.puml`/`.svg` set
   (`scripts/render_skeleton_diagrams.py`). Adding a skeleton invalidates both; the
   `skeleton-promotion` workflow now checks them because of this PR.
5. Full suite. The 6 skips should become passes.
6. `check_promotion_bundle.py` will still fail on the missing lineage sidecar (AL-014, open, needs the
   authored-bundle proof path).

## 6. Environment traps, each hit for real in this session

### 6.1 graphviz is absent, and PlantUML fails silently

PR #415 documented this and it caught us too: with no `dot` on PATH, PlantUML renders structurally
**empty** SVGs and exits 0. The three diagrams committed on the story branch are broken:

| File | bytes | `<text>` elements |
| --- | --- | --- |
| `the-ninth-hand.svg` (746 nodes) | 40,005 | **18** |
| `the-sunless-march.svg` (305 nodes) | 22,963 | **18** |
| `the-vault-of-nine-iron.svg` (305) | 22,890 | **18** |
| `the-ashfall-expedition.svg` (505, rendered elsewhere) | 716,576 | 1,684 |

They are **not** in PR #416 (diagrams were excluded from the split), so the PR is unaffected. They
must be re-rendered before the story push, and the `--check` guard will not catch this: it compares
committed output to freshly generated output, and both are equally empty without graphviz.

### 6.2 Commits are unsigned despite `-S`

The project requires signed commits. In this environment `user.signingkey` points at
`/home/claude/.ssh/commit_signing_key.pub`, which exists but is **0 bytes**, so `git commit -S`
produces an unsigned commit and `%G?` reports `N`. Every commit on both branches is affected and will
need re-signing, or a squash-and-sign, if branch protection requires it. Note #415 and #418 both
report GPG-signed commits, so the local team's setup does not have this problem.

### 6.3 `basedpyright` was unavailable

Not installed in this environment, so **CI is the first strict type-check** for everything in PR #416.
`ruff check` is clean. #415 and #418 both report `basedpyright src/` clean, so expect the bar to hold.

### 6.4 Helper scripts live in a session-scoped scratchpad and are gone

The one-off tools used to build and repair the stories were never committed. If the story work is
resumed, these will need rebuilding (all were small):

- `rl13fix.py`: the sentence join/split retuner behind AL-005. The two guards are the load-bearing
  part: only downcase a folded-in leading word if it is seen lowercase somewhere in the corpus and
  never capitalised mid-sentence; only split where both sides are 8+ words and the right side opens
  with a subject.
- `b3convert.py`: converted the 45 shallowest failure leaves into vigor-costing pass-throughs (AL-026).
- `play3.py`: drove `player/engine.StoryEngine` breadth-first to prove a named ending reachable.
- `prosecheck.py`, `b3analyze.py`, `genbook3.py`: coverage/FK reporting, depth analysis, room-shape
  generation.

`scripts/build_series_book.py` **is** committed and is the one that matters: it compiles the FILL
skeleton and the filled story from one spec so the two cannot drift (AL-001).

## 7. Open work, by priority

Full detail with proposed changes is in the lessons log; this is the triage view.

**Blocks the story push**

- **AL-044** book 2's shape fails `check_incell_clones`. Owner decision, section 5.
- **AL-014** no hand-authored skeleton can pass `check_promotion_bundle` (lineage sidecar required
  unconditionally). Proposed fix: an authored-bundle proof path with an origin sidecar, failing closed
  when neither sidecar is present.

**Large, each its own change**

- **AL-046** the fill orchestrator is one-shot against a 32k output cap; 13 of 26 committed fills
  exceed it and selection has no feasibility predicate, so the matcher can hand the pipeline a book it
  cannot finish. Cheap half first: a feasibility predicate plus a test.
- **AL-036** at ceiling scale the review surface cannot deliver the human approval ADR-005 requires:
  whole blob shipped, 746 passages unvirtualized, no pagination, no per-node review state, one Approve
  button at the bottom.
- **AL-034** one import is ~2,986 sequential provider round trips inside a single Postgres transaction
  holding a `FOR UPDATE` lock, 40-100 minutes against a transaction-mode pooler, no checkpoint.
- **AL-039** repair and the Stage 1 fidelity gate are structurally impossible at this size and both
  fail open; fidelity also embeds untrusted prose without the `<untrusted_passage>` fence that
  `moderation/stages.py` documents as `#CRITICAL: security`.
- **AL-019 / AL-020** reader-path retention. Designed in
  [reader-path-engagement-design.md](./reader-path-engagement-design.md); needs four owner decisions
  (retention window, idle threshold, minimum population, whether guardians see stop points) before any
  table is created. The purge must ship with the table.
- **AL-028 / AL-029 / AL-030 / AL-032** frontend: the endings denominator at M=232, the progress bar
  measuring corpus coverage, every page turn replaying the whole read, and a reconnect path that can
  teleport a child backwards from their own queued past.

**Small and self-contained**

- **AL-040** rescreen runs its whole sweep in one synchronous request.
- **AL-050** three committed fills still cannot pass the gate (verified still failing on `main` at
  `85de102`); quarantined under strict xfail so migrating one forces the list to be pruned.
- **AL-052** triage the 13 read-time drifts and 6 ending-mix outliers PL-23/PL-24 surfaced.

## 8. Reproducing the verification

```bash
uv sync --extra api --extra dev

# the PR's own gates
uv run python scripts/check_lessons_log.py
uv run python -m pytest tests/unit -q
uv run ruff check src/ scripts/ tests/

# author feedback, on any skeleton
uv run python scripts/check_skeleton.py skeletons/16+/<slug>.json --headroom

# the story artifacts (only on the story branch)
uv run python scripts/run_story_gate.py out/<slug>.filled.json
uv run python scripts/check_fill_integrity.py skeletons/16+/<slug>.json out/<slug>.filled.json
uv run python scripts/build_series_book.py --series out/the-vault-of-nine-iron.filled.json \
    out/the-sunless-march.filled.json out/the-ninth-hand.filled.json

# the gates that decide the story push
uv run python scripts/check_incell_clones.py
uv run python scripts/calibrate_mutation_floors.py --check
uv run python scripts/render_skeleton_diagrams.py --check   # needs graphviz, see 6.1
```

## 9. Decisions needed from the owner

1. **Book 2's shape** (section 5): restructure, or an explicit series-continuity allowlist entry.
2. **The two Wyrmreach docs** currently in PR #416 (`wyrmreach-series-design.md`,
   `wyrmreach-series-report.md`): keep them with the process work, where they are the evidence base
   every lesson cites, or move them to the story push.
3. **The reader-path four** (AL-019/AL-020), listed in section 7.
4. **PL-17's shape** (AL-026): the endings floor pushes a gamebook author toward terminal leaves, and
   book 3 now sits exactly on that floor with no headroom. Whether the floor is right for gamebooks is
   a framework question, not a story one.

## 10. Related documents

- [Authoring lessons log](./authoring-lessons-log.md), the tracker for everything in section 7
- [Story quality lessons](./story-quality-lessons-2026-07.md), the narrative behind AL-001..AL-023
- [Adversarial review record](./reviews/ceiling-scale-review-2026-07-25.md), raw evidence and
  measurements for the reader, import/publish and catalog reviews
- [Reader path and engagement design](./reader-path-engagement-design.md)
- [Wyrmreach series design](./wyrmreach-series-design.md) and
  [build report](./wyrmreach-series-report.md)
- [Validation rule catalog](./validator-rules.md), the target of section 4.2
- PRs [#415](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/415) (diversity, SR-9, L2-14,
  clone gate), [#417](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/417) and
  [#418](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/418) (ADR-023 personalization,
  sentinel stripping in RL-13)
