---
title: "Handoff: Measurement Workstream, 2026-08-15"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "State of the story-quality measurement workstream at handoff: what landed, what is decided, what is open, and the three traps the next team will otherwise hit."
tags:
  - planning
  - measurement
  - handoff
component: Development-Tools
---

# Handoff: Measurement Workstream, 2026-08-15

> **Branch**: `claude/story-dev-testing-eval-bm0tpf` at `d297ed5`
> **Suite**: 7793 passed, 1402 skipped, 3 xfailed (the xfails are pre-existing pre-schema-v2 fills)
> **Gates**: `ruff check`, `ruff format --check`, `basedpyright src/` (0 errors),
> `check_lessons_log.py`, `check_work_linkage.py` all clean

## Read this first: the branch does not merge cleanly

`main` squash-merged PR #708 as `0396507` while this branch carries the same work as ~35
individual commits, and `main` has since taken #709, #712, #714 and two releases. A test merge
produces **155 conflict hunks across 25 files**. The conflicts are mostly mechanical (one side
empty, the other adding), but three files need real judgement because both sides changed them for
different reasons:

| File | Why both sides moved |
| --- | --- |
| `validator/paths.py` | #712 added the zero-edge reading and a `Draw.count` guard; this branch added nothing here after W1 |
| `scripts/compare_vendors.py` | #712 added duplicate-vendor-label rejection; this branch has the older harness |
| `validator/reading_level.py` | This branch rebuilt the syllable counter and made RL-13 one-sided; `main` has neither |

**Recommended resolution order**: take `main` wholesale for `paths.py`, `compare_vendors.py` and
their tests, since `main` is strictly newer there and this branch changed nothing in them after
W1. Take this branch wholesale for `reading_level.py`, `reading_level_loop.py`, `continuity.py`,
`imitable.py`, `utils/sentences.py`, `policy.py` and the two ledgers. Everything else is
additive on one side only.

Do NOT rebase. The two ledgers (`authoring-lessons-log.md`,
`unscheduled-work-register.md`) are append-only and both sides appended; a rebase replays that
conflict once per commit.

## What landed

Eleven register items closed or advanced. Every figure below is reproducible from the repo; none
is quoted from a report.

### The syllable counter, and everything downstream of it

`validator/reading_level.py::_count_syllables` was rebuilt against CMUdict as ground truth
(`AL-388`). This is the single highest-leverage change on the branch, because the counter feeds
the gate, the whole-book aggregate, and the generation repair loop.

| | before | after |
| --- | --- | --- |
| dictionary types (115,901 words) | 83.03% | 90.32% |
| corpus tokens (390,334) | 94.21% | 99.14% |
| FK grade bias | +0.268 | -0.031 |

Both hash-halves of the dictionary land within 0.2 points, so the rules generalise rather than
memorise. `ea`, `ie` and `io` splits were measured and **rejected** for being majority-digraph;
`lion`, `poem` and `cereal` ship knowingly wrong and `tests/unit/test_syllable_accuracy.py`
records the trade.

Three consequences followed, and the second is the one that matters most:

1. Every committed book reads ~0.27 grades easier than it used to (`AL-389`). Nothing about the
   prose changed; the books were always easier than they declared and the over-count was propping
   them into band.
2. **RL-13 is now one-sided at 3-5 and 5-8** (`AL-399`), and so is the repair loop. The loop's
   acceptance test was symmetric, so with an accurate counter it would have accepted revisions
   making young-band prose *harder* in order to reach target. Corpus warnings go 331 to 307, all
   removed at those two bands. The targets were deliberately **not** moved: they are claims about
   readers, and shifting them would bake the counting bug into the spec.
3. Per-band drafting guidance was re-derived from the corpus (`AL-390`). Sentence length carries
   about three quarters of the grade spread (5.7 to 21.0 words per sentence across bands) and
   vocabulary almost none (1.21 to 1.37 syllables per word), which inverts the advice authors were
   giving each other. The irregular-past rule was dropped outright: it saved 10 syllables over ten
   pairs under the broken counter and 1 under the corrected one.

### The judge panel

`judge-gemini-3.1` is **removed**. Three independent lines converged on it, none available when
the panel was chosen:

- excluding it dropped W7's control-noise floors 2 to 6 times;
- per criterion it is the outlier on four of seven and correlates *negatively* with both others on
  `choice_quality` (-0.15, -0.02) where they agree at +0.46 (`AL-392`);
- run to run on identical arms it averages 0.323 absolute movement against gpt-5.6's 0.120, owning
  every movement past a full scale point (max 1.710 against 0.290) (`AL-397`).

**Any W7 verdict computed with it in the panel should be re-derived, not carried forward.**

W7's agreement statistic was also replaced (`UW-C251`): the retracted +0.16 / +0.58 / +0.14 came
from rounding each judge's mean across all seven criteria and running unweighted kappa.
`scripts/w7_agreement.py` now reports Spearman over within-book deltas and quadratic-weighted
kappa over raw scores, per criterion, with marginals printed beside both.

### New measures, both deliberately not gates

- `validator/continuity.py` measures optional history (ancestors minus dominators). It is exact
  and flags 3,815 of 4,472 nodes, which is correct and useless per node. Its value is the
  aggregate: all six `time_cave` books report **zero** across 236 nodes.
- `validator/imitable.py` routes 13 of 167 young-band endings to human attention, catching all
  three endings two independent readers named. Six of the thirteen are one lantern-festival book,
  which is the right failure mode for a router and disqualifying for a gate.

### Tooling

- `utils/sentences.py`, one shared splitter replacing four crude ones. Three callers migrated
  after measuring the change over 31 books; **two deliberately not migrated** with reasons
  recorded (`dialogue.py::sentence_share` shifts ~25% in 12 books and is panel-calibrated).
- `scripts/_paid_output.py` refuses a gitignored output destination before any provider call.
- `w7_battery.py` journals each scoring to `journal.jsonl`, flushed per line.
- PL-23 now reports its breach **direction** at skeleton time.

## Decisions already made, so nobody relitigates them

| Decision | Ruling |
| --- | --- |
| Band FK targets | Not moved. RL-13 goes one-sided at 3-5/5-8 instead. |
| `loop_and_grow` at Tier 1 | **Legal**, per ADR-011. Do not gate it. ADR-011 amended so its purpose column stops telling young-band authors to accumulate. |
| `gemini-3.1` | Dropped from the panel. |
| Continuity as a rule | Withdrawn. All three formulations measured and none usable. |
| `imitable_practice` as a judged criterion | Not built. Must pass W7 before it arbitrates. |

## Open work

| Item | State |
| --- | --- |
| `UW-C253` | Partly measured. Run-to-run spread is known at leg level; **per-criterion spread still unmeasured** and needs one completed run. |
| `UW-C250` | Needs the same completed run (control-versus-control). |
| `UW-C259` | Screen shipped; the judged criterion is unbuilt pending W7 validation. |
| W8, W9, W10, W14 | Unblocked (the `UW-C239` pricing blocker in the workplan table is **stale**, the table has been complete since 2026-08-14). Budget-bound: roughly $30-50 against ~$11 remaining. |
| W11, W12, W13 | Deferred by design (W11 needs W7; W12 behind ADR-018 consent scoping; W13 behind W12). |
| Reviewer distillation | Parked at Phase 0 by owner ruling until the drafting workstream completes. |

## Three traps

**1. Paid runs do not survive this environment.** Three consecutive W7 runs were killed by
container restarts, after 92, 34 and 20 scorings. Two produced nothing because results were held
in memory and written at the end; the third survived because journalling had landed. Roughly
$2.31 bought no durable artifact. **Do not assume a run completes unattended.** Commit
`journal.jsonl` mid-flight; `out/w7-run3/journal.jsonl` is a worked example of a partial run whose
data is still usable.

**2. Register rows are hypotheses, not specifications.** Four claims recorded when the symptom was
fresh did not survive being checked against the thing they described:

- `AL-384`'s incidence of 40 of 61 was wrong; the true figure is 37 of 61 (12 under, 25 over).
  The error was a one-off script that diverged from the gate's own path helper.
- `UW-C256`'s premise that PL-23 runs only at fill time was wrong; it already ran at skeleton
  context.
- `UW-C255`'s quoted node text does not exist in the corpus; it is a composite of two real strings.
- `UW-C258`'s proposed `loop_and_grow` gate contradicted ADR-011.

Start every ticket by reproducing its stated claim, and prefer reusing the production code path
over writing a measurement script beside it. Two of the four errors share that root: a script
written to measure what the codebase already computes will diverge, invisibly, because both sides
produce plausible numbers.

**3. A frontier reader's converged pattern is reliable; its instances are not.** Of four
blind-spot instances checked against the book JSON, one was refuted outright, two were overstated,
and one was verified, while every class they belonged to was real. A reader cannot enumerate paths.
The procedure is written up in `blind-spot-review-brief.md`; the verification step is not optional.

## Where things are

| Artifact | Path |
| --- | --- |
| Lessons `AL-378`..`AL-400` | `docs/planning/authoring-lessons-log.md` |
| Register `UW-C250`..`UW-C260` | `docs/planning/unscheduled-work-register.md` |
| Blind-spot procedure | `docs/planning/blind-spot-review-brief.md` |
| Reader reports and verifications | `out/reviews/` |
| W7 agreement report | `out/w7/agreement.txt` |
| Run-to-run analysis | `out/w7-repeat/run-to-run.txt` |
| Partial run 3 journal | `out/w7-run3/journal.jsonl` |
| Band guidance | `docs/planning/drafting-guide.md`, `.claude/skills/cyo-author/SKILL.md` |
| ADR amendment | `docs/planning/adr/adr-011-story-scale-framework.md` |

## Related documents

- [Measurement workplan](./cyo-measurement-workplan-2026-08-12.md), W1-W15 with pre-registered rules
- [Authoring lessons log](./authoring-lessons-log.md)
- [Unscheduled work register](./unscheduled-work-register.md)
- [Blind-spot review brief](./blind-spot-review-brief.md)
