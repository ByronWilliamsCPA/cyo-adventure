---
title: "Authoring Lessons Log"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Append-only log of lessons learned from each story development run, so recurring problems become tooling changes instead of re-learned folklore."
tags:
  - planning
  - authoring
  - quality
  - process
component: Development-Tools
source: "story-quality-lessons-2026-07.md"
---

# Authoring Lessons Log

> **Status**: Accepted | **Updated**: 2026-07-25
> **Serves**: [A11](./capability-register.md) (structural quality tools across the corpus)
> **Validated by**: `uv run python scripts/check_lessons_log.py`

Every story development run appends here. The point is that a lesson learned once becomes a
**change to the tooling** rather than folklore an author has to rediscover, so each row carries a
proposed change and a status that tracks whether it landed.

## How to use this log

**When to append.** At the end of any authoring run: a new story or series book, a skeleton
promotion, a fill pass, or a validator/gate change made in service of authoring. If the run
produced no lesson, append nothing; an empty run is a real outcome.

**What counts as a lesson.** Something a future author or a future tooling change should act on.
Three tests, any one of which qualifies it:

1. It cost real iteration to discover (a rule interaction, a calibration, an ordering constraint).
2. The tooling let a defect through, or reported it in a way that did not point at the cause.
3. It would be re-learned from scratch by the next person, because nothing in the repo records it.

A one-off typo is not a lesson. "The gate reports band membership, so the floor reads as a pass"
is.

**Fields.**

| Field | Rule |
| --- | --- |
| `ID` | `AL-NNN`, sequential, never reused or renumbered. |
| `Date` | ISO date the lesson was recorded. |
| `Source` | The run that produced it (story slug, series book, or workstream). |
| `Category` | One of `validator`, `tooling`, `authoring-craft`, `scale`, `metadata`, `process`, `docs`, `product`. |
| `Lesson` | What is true, stated so it is actionable without reading the source run. |
| `Proposed change` | The change that would stop this recurring, or `none (craft note)` when the lesson is guidance rather than a code change. |
| `Status` | `open`, `accepted`, `applied`, `rejected`, or `superseded`. |
| `Ref` | Commit, PR, file, or doc. **Required** when status is `applied`, `rejected`, or `superseded`. |

**Review cadence.** Sweep the `open` rows whenever a phase is planned. An `open` row that has
survived two phase boundaries is either genuinely low value (mark it `rejected`, with the reason in
`Ref`) or it is real debt being avoided; either way, decide rather than let it sit.

**Status discipline.** `accepted` means the change is agreed but unbuilt, and it must appear in a
plan somewhere. `applied` means the change is merged and the `Ref` proves it. Nothing moves to
`applied` on the strength of intent.

---

## Log

| ID | Date | Source | Category | Lesson | Proposed change | Status | Ref |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AL-001 | 2026-07-25 | wyrmreach b1-b3 | tooling | Compiling the FILL skeleton and the filled story from one spec makes drift between them structurally impossible; two hand-maintained artifacts drift silently. | Keep one-spec compilation as the authoring pattern for any multi-artifact story. | applied | `scripts/build_series_book.py` |
| AL-002 | 2026-07-25 | wyrmreach b2 | authoring-craft | In a `carries_state: true` continuation a carried variable initialises `true`, so every `== false` condition on it is unsatisfiable and a hard L2-11. Carried state must be read-only; acquisition moves to a new book-local variable. | none (craft note); recorded in the series design doc's carried-variable rule. | applied | `wyrmreach-series-design.md` section 4 |
| AL-003 | 2026-07-25 | wyrmreach b2, b3 | validator | A gate on a *new* variable placed earlier in the graph than any node granting it is also an L2-11 dead branch. This is the same class as AL-002 but not obvious from the rule text. | Add a cause hint to the L2-11 message for both patterns; it also improves the Stage C repair prompt, which gets findings verbatim. | open | `story-quality-lessons-2026-07.md` finding I |
| AL-004 | 2026-07-25 | wyrmreach b1-b3 | authoring-craft | Flesch-Kincaid is driven by sentence count, not passage length: at a fixed ~60 words the same content scores FK 5 in four or five sentences, 9-11 in three, 13+ in two. The practical 16+ rule is three sentences per passage. | none (craft note); recorded in the series design doc's reading-level section. | applied | `wyrmreach-series-design.md` section 6 |
| AL-005 | 2026-07-25 | wyrmreach b3 | authoring-craft | An RL-13 outlier can be retuned without rewriting a word by joining or splitting sentence boundaries; 185 of 212 cleared this way. Two guards are required: only downcase a folded-in leading word if it is seen lowercase in the corpus and never capitalised mid-sentence, and only split where both sides are 8+ words and the right side opens with a subject. | none (craft note); the guards are the reusable part. | applied | `wyrmreach-series-report.md` N8 |
| AL-006 | 2026-07-25 | wyrmreach b3 | validator | RL-13 scores `<<FILL>>` directive text, so every skeleton emits one warning per node (746 for a ceiling-scale book), training reviewers to ignore the rule. PL-19 already skips FILL bodies and is the pattern to copy. | Skip bodies containing the FILL marker in `check_reading_level`; hoist the marker constant so both modules import it. | open | `story-quality-lessons-2026-07.md` finding E |
| AL-007 | 2026-07-25 | wyrmreach b1 | authoring-craft | The Layer-2 configuration key includes the visited set of nodes carrying `once` effects, so each `once` effect doubles the config space. In an acyclic graph `once` is redundant, because no node is entered twice on a path. | none (craft note): never use `once` in a DAG-shaped story. | applied | `wyrmreach-series-design.md` section 6 |
| AL-008 | 2026-07-25 | wyrmreach b3 | authoring-craft | Declare a carried integer variable's range as what the continuation can actually reach, not what the variable could theoretically hold. Narrowing `renown` to 3-5 and dropping an unreachable carried flag is the difference between 36,781 configurations and risking the 100k L2-12 cap. | none (craft note); it is also the more truthful model. | applied | `wyrmreach-series-design.md` section 4 |
| AL-009 | 2026-07-25 | wyrmreach b3 | scale | A ceiling-scale gamebook needs breadth, not length: rooms hung as parallel chains off an act hub and reconverging on an act gate fit 746 nodes inside 74 of 93 permitted hops, and keep a reader's route at 52 nodes. | none (craft note); the shape is recorded as the six room shapes. | applied | `wyrmreach-series-design.md` section 5 |
| AL-010 | 2026-07-25 | wyrmreach b3 | process | Generate wiring, never voice. Structure was generated from six formal room shapes and every beat, label and ending title was then authored over it through a patch keyed by node id, with an assertion that label count equals choice count. That assertion caught eleven real mismatches that would have shipped as generated text. | Keep the two-stage split for any story past the ~460-node hand-authoring ceiling; the label-count assertion is the load-bearing part. | applied | `wyrmreach-series-report.md` N7 |
| AL-011 | 2026-07-25 | wyrmreach b3 | scale | L2-13 firing past 460 nodes is the expected and correct output, not a defect: it states that the completed Layer-2 walk, not human review, is the sole correctness guarantee. At that scale the walk has to be treated as the acceptance test rather than a lint pass. Every structural problem in book 3 was found by L2-11 or the budget report, none by reading the spec. | none; behaviour is correct as designed. Document it so the warning is not "fixed" by someone later. | accepted | `story-quality-lessons-2026-07.md` finding N6 |
| AL-012 | 2026-07-25 | wyrmreach b1-b3 | metadata | `metadata.estimated_minutes` is ADR-011's fastest-finish clock, and nothing validates it, so on a hand-authored or imported book it is whatever the author typed. All three books were wrong by 3-6x (40/40/90 declared against 8/8/14 canonical). | Fixed in the books. Still open: a PL-series advisory comparing the declared value against `mutation/identity.py::recompute_estimated_minutes`, which already exists and is tested. | applied | commit `86dafda` (books); gate advisory tracked as AL-021 |
| AL-013 | 2026-07-25 | wyrmreach b1-b3 | validator | PL-19 reports band membership only, so the 55 words/node advisory floor reads as a pass when the cell target is 80. Authoring to the floor put books 1 and 2 below their cell's intended whole-world range (77 and 82 minutes against ~110-175) and dragged the fastest-finish clock under its cell target. | Report distance from target, not just band membership. Consider a tighter two-sided band for `production_eligible` stories, keeping the wide band for MVP/test tiers. | open | `story-quality-lessons-2026-07.md` finding D |
| AL-014 | 2026-07-25 | wyrmreach b1-b3 | tooling | No hand-authored skeleton can pass the `skeleton-promotion` CI gate: `check_promotion_bundle.py` requires a lineage sidecar unconditionally, and no sidecar exists anywhere in `skeletons/`. The thirteen existing hand-authored skeletons are green only because CI proves changed files and none has been touched since the workflow landed. | Add an authored-bundle proof path (origin sidecar, `check_skeleton`, theme contract when present, WS-5 anti-clone floor), failing closed when neither sidecar is present. Not an exemption. | open | `story-quality-lessons-2026-07.md` finding A |
| AL-015 | 2026-07-25 | wyrmreach b3 | validator | Nothing checks the within-story ending mix. Book 3 is 118 death endings of 232 (51%) and gates clean; a 95%-death book would too. The normalised kind and valence histograms already exist in `diversity/structure.py`, used only for between-story anti-clone distance. | A PL-series advisory over the existing histograms: warn when one ending kind exceeds a per-band share, or positive-valence endings fall below a floor. | open | `story-quality-lessons-2026-07.md` finding F |
| AL-016 | 2026-07-25 | wyrmreach b2 | process | A comparison check is only as good as the independence of its two inputs. A builder bug wrote the prose story to the skeleton path, so `check_fill_integrity.py` compared a file with itself and **passed**, silently making an earlier verification vacuous. A check that cannot fail manufactures confidence. | Give `check_fill_integrity.py` a self-test: assert the two inputs are not the same file, that the skeleton contains FILL markers, and that the filled story contains none. Apply the same reasoning to any proof comparing two generated files. | open | `story-quality-lessons-2026-07.md` finding J |
| AL-017 | 2026-07-25 | wyrmreach b3 | docs | The rule catalog has drifted from the code it documents, despite stating that rule changes require a revision to it: L2-13 is absent entirely, and RL-13's entry says the grade is "computed by textstat" when the implementation is deliberately vendored and textstat is not a dependency. `_MIN_WORDS_FOR_FK` (20) is also undocumented and changes which nodes get scored. | Add the L2-13 row, correct RL-13, bump the catalog version, and add a test asserting every rule id the validator can emit appears in the catalog. | open | `story-quality-lessons-2026-07.md` finding G |
| AL-018 | 2026-07-25 | wyrmreach b1-b3 | tooling | The budget-headroom report is what made ceiling-scale authoring tractable (nodes against the cell, endings and decisions against floors, word mean, depth against the cap, fastest finish against the arc floor, ending mix). It lives in a series-only script; `check_skeleton.py` prints pass or fail with no sense of proximity to any edge. | Move the headroom report into `check_skeleton.py`, computed from the typed Storybook rather than a spec format, so the generation pipeline and the guardian editor get it too. | open | `story-quality-lessons-2026-07.md` finding H |
| AL-019 | 2026-07-25 | wyrmreach b1-b3 | product | No reader outcome ever reaches an author. `Completion`, `ReadingState.path` and `Rating` all exist and `StorybookVersion.skeleton_slug` links a version to its skeleton, but `Completion` is read in five places and every one is a per-child read. Nobody can say which of book 3's 232 endings any reader has reached, or where readers stop. | Designed: reader-path retention plus a de-identified engagement rollup, under S12's minimum-population constraint. | accepted | `reader-path-engagement-design.md` |
| AL-020 | 2026-07-25 | wyrmreach b1-b3 | product | The offline client already transmits the full accumulated `path` on every save (`frontend/src/offline/sync.ts::toPutPayload`), and the server overwrites it (`api/reading.py`, `row.path = list(body.path)`). The route data we want for engagement analysis already arrives and is discarded, so retaining it needs no client change and no request-contract change. | Append an immutable trail row on each reading-state write; see the design doc. | accepted | `reader-path-engagement-design.md` section 3 |
| AL-021 | 2026-07-25 | wyrmreach b1-b3 | validator | Split from AL-012 so the gate change is tracked separately from the book fix: the declared/derived read-time mismatch is undetectable today. | Add the PL-series `estimated_minutes` advisory comparing declared against `recompute_estimated_minutes`, tolerance ~25%, advisory not blocking. | open | `story-quality-lessons-2026-07.md` finding B |
| AL-022 | 2026-07-25 | wyrmreach b1-b3 | product | `estimated_minutes` is the fastest-finish clock, so a 746-node, 42,085-word gamebook whose whole-world clock is 3.2 hours advertises "14 min" to a child choosing a book. Technically correct, practically a broken promise. ADR-011 defines the whole-world clock; the schema surfaces one field. | Derive both clocks, add `estimated_minutes_whole_world`, and show "about 15 minutes to finish, hours to explore" on the kid and guardian surfaces. Owner decision, not an implementation detail. | open | `story-quality-lessons-2026-07.md` finding B |
| AL-023 | 2026-07-25 | wyrmreach b1-b3 | tooling | The shipped client never sends `choice_path`, so the server-side engine replay that exists to stop a forged `current_node`/`var_state`/`path` is dormant (`api/reading.py` carries the `#ASSUME` admitting it). Any analytics derived from the client-supplied `path` is therefore unverified reader-reported data. | Enable `choice_path` in `toPutPayload` and make the replay authoritative before trail data is used for anything beyond directional signal. Security and data-integrity relevance, not only analytics. | open | `reader-path-engagement-design.md` section 6 |

---

## Related documents

- [Story quality lessons from the Wyrmreach build](./story-quality-lessons-2026-07.md), the narrative behind AL-001..AL-023
- [Wyrmreach series build report](./wyrmreach-series-report.md), the run that produced them
- [Reader path and engagement design](./reader-path-engagement-design.md), the design AL-019/AL-020 point at
- [Capability register](./capability-register.md), A11
- [Validation rule catalog](./validator-rules.md), the target of AL-003, AL-006, AL-013, AL-015, AL-017, AL-021
- [Template feedback](../template_feedback.md), the parallel log for issues belonging to the cookiecutter template rather than to authoring
