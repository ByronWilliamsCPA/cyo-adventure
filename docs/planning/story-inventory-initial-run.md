---
title: "Initial story inventory: subagent authoring run (one story per cell)"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Execution plan for the first full authoring run: use supervised subagents to
  fill every production skeleton so each age-band x length combination has one story,
  with a per-story compliance evaluation loop (deterministic gate + independent
  reviewer) before anything is imported or published; plus a skeleton-expansion wave
  where Fable designs two additional skeletons per production cell."
tags:
  - planning
  - generation
  - authoring
  - compliance
---

# Initial story inventory: subagent authoring run

> **Status**: Proposed (2026-07-17)
> **Relates to**: [ADR-011](./adr/adr-011-story-scale-framework.md) (story-scale matrix),
> [ADR-005](./adr/adr-005-mandatory-human-approval.md) (human approval gate),
> `.claude/skills/cyo-author/` (fill procedure), `validator/` (offline gate).

## TL;DR

Fill all 18 production skeletons (14 prose cells covering every offered age x length
combination, plus 4 gamebook style variants) using parallel subagents, one story per
cell. Each story runs a fixed per-story pipeline: **author fill (chunked) -> scripted
integrity checks -> offline validation gate -> independent compliance review ->
supervisor adjudication -> bounded repair loop**. Authors are Haiku (bands 3-5, 5-8) or
Sonnet (8-11 and up); Opus is escalation-only. A separate **skeleton-expansion wave
(Wave 5)** has Fable design two additional skeletons for each of the 18 production
cells (36 new skeletons, bringing the catalog to 3 per cell), each passing scripted
structural validation and an independent design review. Nothing is imported to the
database or published in this run: the deliverables are filled story JSONs in `out/`,
new skeletons under `skeletons/`, a compliance/design report per artifact, and a
coverage summary, all committed for human review per ADR-005.

## 1. Objective and scope

Build the initial inventory so that **every offered age-band x length combination has
exactly one authored, gate-passing, compliance-reviewed story**.

- The ADR-011 matrix offers 14 age x length combinations (prose). Young bands cap at
  Medium; 13-16 and 16+ start at Medium. Off-matrix combinations (for example 3-5
  Long or 16+ Short) do not exist by design and are rejected by PL-21; they are out of
  scope, not gaps.
- The 4 gamebook cells (13-16/16+ x Medium/Long) are **style variants** of combinations
  already covered by prose. They are Wave 4, optional, and run only after the prose
  waves are signed off.
- MVP-tier skeletons (`the-lost-mitten`, `the-clocktower-cipher`, `the-sunken-signal`)
  are excluded: they are non-production seeds and two already have fills in `out/`.
- **Skeleton expansion (Wave 5)**: Fable designs 2 additional skeletons for every one
  of the 18 production cells (36 new skeletons), growing the catalog to 3 skeletons
  per cell (section 6.1). Designing skeletons is in scope; **filling** the new
  skeletons is not; a follow-on run reuses the Wave 1-4 machinery for that.
- Import into Postgres and publication are **out of scope for this run** (section 8).

## 2. Coverage matrix (cell -> skeleton)

Every production cell already has exactly one production-eligible skeleton
(`production_eligible: true`, all Tier 1, no state variables), so Waves 1-4 are
prose-fill only; structural authoring happens exclusively in Wave 5, which adds 2 more
skeletons per cell (section 6.1).

| Band | Length | Style | Skeleton | Nodes | Topology | Wave | Author model |
| --- | --- | --- | --- | ---: | --- | :-: | --- |
| 3-5 | short | prose | `the-clover-and-the-butterfly` | 20 | time_cave | 1 | haiku |
| 5-8 | short | prose | `the-lantern-festival` | 36 | loop_and_grow | 1 | haiku |
| 8-11 | short | prose | `the-cave-of-echoes` | 64 | time_cave | 1 | sonnet |
| 3-5 | medium | prose | `the-teddy-bears-picnic` | 29 | loop_and_grow | 2 | haiku |
| 5-8 | medium | prose | `the-backyard-treasure-map` | 61 | time_cave | 2 | haiku |
| 10-13 | short | prose | `the-midnight-museum` | 94 | branch_and_bottleneck | 2 | sonnet |
| 8-11 | medium | prose | `the-sky-ship-stowaway` | 111 | branch_and_bottleneck | 2 | sonnet |
| 13-16 | medium | prose | `the-signal-in-the-static` | 123 | branch_and_bottleneck | 2 | sonnet |
| 16+ | medium | prose | `the-last-train-north` | 143 | branch_and_bottleneck | 2 | sonnet |
| 10-13 | medium | prose | `the-hollow-lighthouse` | 148 | branch_and_bottleneck | 2 | sonnet |
| 8-11 | long | prose | `the-clockwork-menagerie` | 166 | branch_and_bottleneck | 3 | sonnet |
| 13-16 | long | prose | `the-vanishing-orchard` | 177 | branch_and_bottleneck | 3 | sonnet |
| 10-13 | long | prose | `the-mapmakers-island` | 224 | branch_and_bottleneck | 3 | sonnet |
| 16+ | long | prose | `the-salt-archive` | 225 | branch_and_bottleneck | 3 | sonnet |
| 13-16 | medium | gamebook | `the-sunspire-ascent` | 252 | branch_and_bottleneck | 4 | sonnet |
| 16+ | medium | gamebook | `the-drowned-court` | 314 | branch_and_bottleneck | 4 | sonnet |
| 13-16 | long | gamebook | `the-thornwood-trial` | 375 | branch_and_bottleneck | 4 | sonnet |
| 16+ | long | gamebook | `the-ashfall-expedition` | 505 | branch_and_bottleneck | 4 | sonnet |

## 3. Model policy for subagents

Per project direction: **subagents run Sonnet or Haiku; Opus only when a story's
complexity requires it.**

- **Author agents**: Haiku for bands 3-5 and 5-8 (short sentences, 40-70 words/node,
  tightly beat-scripted); Sonnet for 8-11 and up.
- **Compliance reviewer agents**: Sonnet for every story, always a fresh agent that did
  not write the prose (independence is the point).
- **Integrity checks**: scripts, not agents (section 5.1); zero model cost.
- **Opus escalation, allowed only when**: (a) a story fails its repair loop twice
  (section 7), or (b) a Wave 3/4 fill shows sustained quality failures at Sonnet
  (reviewer rejects two consecutive revisions for craft, not mechanics). Escalation
  replaces the author model for the failing nodes only, and the supervisor records why
  in the story's compliance report.
- **Skeleton design (Wave 5) is the explicit exception**: designer agents run
  **Fable** by product direction, because graph design (topology, reconvergence,
  arc floors, ending economies at up to ~500 nodes) is the hardest task in the run.
  Skeleton **design reviewers** run Opus; the deterministic structural checks stay
  scripted (section 6.1).
- The supervisor (main session) does not delegate adjudication: it reads every gate
  report and reviewer verdict itself.

## 4. Roles

- **Supervisor (main session)**: owns the task list (one task per story), launches
  agents in parallel (3-4 concurrent story pipelines), adjudicates every verdict,
  enforces the repair-loop bound, commits artifacts per wave.
- **Author agent (one per story)**: follows `.claude/skills/cyo-author/SKILL.md`.
  Receives the skeleton path, the band's enforced envelopes (from
  `validator/band_profile.py`, not the stale SKILL.md table; see section 9), and a
  fixed output path `out/<slug>.filled.json`. Fills in **chunks of ~30 nodes** with a
  stable preamble (skeleton metadata, band rules, world/character notes) so prompt
  caching works, then self-checks for leftover `<<FILL` markers before returning.
- **Compliance reviewer agent (one per story, fresh context)**: receives the filled
  JSON and the rubric (section 5.2) only; never the author's transcript. Returns a
  structured verdict: pass/fail per rubric category, with node-id-anchored findings.

## 5. Per-story pipeline

```text
skeleton --(A: author fill, chunked)--> out/<slug>.filled.json
        --(B: scripted integrity checks)--> structural diff + word stats
        --(C: offline gate)--> run_gate() report (blocked / warnings)
        --(D: compliance reviewer agent)--> rubric verdict
        --(E: supervisor adjudication)--> approve | repair (back to A, prose only) | halt
        --(F: artifacts)--> out/reports/<slug>.compliance.md
```

### 5.1 Deterministic checks (B and C, scripted)

Run by the supervisor via small scripts added in Wave 0 (a third, for Wave 5 skeleton
validation, is specified in section 6.1):

- `scripts/check_fill_integrity.py <skeleton> <filled>`:
  - **Structural immutability**: strip node body text from both files and compare the
    remainder canonically; any difference (ids, choices, targets, endings, variables,
    metadata) is a hard fail. The author only writes prose; this makes that mechanical.
  - **No `<<FILL` markers** anywhere.
  - **Word stats**: per-node counts, story mean vs the band's advisory band, and any
    node above the per-node hard max (`band_profile.words_per_node_profile`).
- `scripts/run_story_gate.py <filled>`: load JSON, call
  `cyo_adventure.validator.gate.run_gate(data)` (standard scale), print the merged
  report. This needs no database, so it runs in any environment. Gate `blocked=True`
  fails the story; RL-13 reading-level warnings do not block but must be addressed or
  explicitly waived in the compliance report.

### 5.2 Compliance review rubric (D, agent judgment)

This is the "closely evaluate each story" requirement: everything the deterministic
gate cannot judge. Each category is pass/fail with cited node ids.

1. **Age-appropriateness of language**: vocabulary, sentence length, and syntax match
   the band and the skeleton's `reading_level` target.
2. **Fail-state and content policy**: prose never exceeds the band's content-flag
   ceiling in tone (a "mild peril" flag must read mild); no death/capture framing for
   3-5/5-8 even in near-miss phrasing; scariness stays within band.
3. **Beats fidelity**: each node's prose delivers the `beats=` intent of the original
   `<<FILL>>` directive (reviewer receives the skeleton for side-by-side comparison).
4. **Choice setup**: every choice label on a node is a natural, discoverable action
   from that node's prose; no choice appears unmotivated or contradicted.
5. **Continuity**: names, objects, and tone are consistent across all paths into a
   node (reconvergent nodes must read correctly from every parent).
6. **Ending quality**: each ending's prose matches its declared `kind`/`valence`;
   successful endings on the fastest-finish path form a complete arc, not a hollow win.
7. **Safety and provenance**: no PII, no real-brand/IP content, no instructions a
   child could unsafely imitate, no embedded links or metadata oddities.

### 5.3 Artifacts (F)

- `out/<slug>.filled.json`: the approved fill.
- `out/reports/<slug>.compliance.md`: gate report summary, word stats, reviewer verdict
  by category, repair history, model(s) used, final supervisor disposition.
- `out/reports/initial-inventory-summary.md`: the band x length coverage grid with
  per-story status, updated at the end of each wave.

All three are committed to the run branch so the human review (section 8) has a full
audit trail.

## 6. Waves and sequencing

Wave order is smallest-first on purpose: the pilot proves the pipeline cheaply before
the large fills spend tokens.

| Wave | Content | Stories | Approx. prose volume | Gate to proceed |
| :-: | --- | :-: | --- | --- |
| 0 | Tooling: the three scripts (5.1 and 6.1), fix the stale word-target table in `cyo-author/SKILL.md` (section 9), create `out/reports/` | - | - | Fill scripts pass on an existing MVP fill in `out/`; `check_skeleton.py` passes on the 18 existing production skeletons |
| 1 | Pilot: one small story per author model tier (3-5 S, 5-8 S, 8-11 S) | 3 | ~10k words | All 3 approved; supervisor reviews process friction and adjusts prompts/chunk size |
| 2 | Remaining prose Short/Medium | 7 | ~83k words | All approved |
| 3 | Prose Long | 4 | ~103k words | All approved; core objective (14/14 combinations) met |
| 4 | Optional: gamebook variants | 4 | ~106k words | Only on explicit go-ahead after Wave 3 sign-off |
| 5 | Skeleton expansion: Fable designs 2 new skeletons per production cell | 36 skeletons | ~7,000 nodes of graph design (beats, choices, endings) | Independent track; may start any time after Wave 1 confirms tooling |

Parallelism: 3-4 story pipelines at a time within a wave; stages B-D for one story
overlap with stage A of the next (no barrier between stories). Wave 5 is an
independent track (it consumes no fill-pipeline capacity) and can run alongside
Waves 2-4 at supervisor discretion.

### 6.1 Wave 5: skeleton expansion (Fable designers)

Goal: 2 additional skeletons for each of the 18 production cells, growing the catalog
to 3 per cell so `skeleton_match` has real variety and recency weighting has room to
rotate.

**Per-skeleton pipeline** (mirrors the story pipeline, structure instead of prose):

```text
design brief --(A: Fable designer)--> skeletons/<band>/<slug>.json
            --(B: scripted structural validation)--> load_skeleton + cell assertions
            --(C: design review, Opus, fresh context)--> rubric verdict
            --(D: supervisor adjudication)--> approve | repair (bounded) | halt
            --(E: artifact)--> out/reports/skeletons/<slug>.design.md
```

- **Design brief (supervisor-authored, one per skeleton)**: the target cell, the
  required topology, a theme direction, and the cell's numeric contract (node
  envelope, `min_complete_floor`, ending count/fraction, decisions-per-path 4-8,
  choices-per-decision 2-3, 2-3 setup nodes before the first choice).
- **Diversity constraints**: within each cell, the 3 skeletons (1 existing + 2 new)
  must differ in topology wherever the band's ADR-011 allowance offers more than one
  (every current production skeleton at 8-11+ is `branch_and_bottleneck`, so the new
  ones should exercise `open_map`, `sorting_hat` (Medium/Long only), `time_cave`, and
  `gauntlet` (gamebook) as the band allows), and must differ in theme from each other
  and from the existing skeleton.
- **Tier 2 (stateful) option**: at 10-13 and up, one of the two new skeletons per cell
  may declare variables/effects/conditions (loops require state from 10-13 per
  ADR-011). Tier-2 shells get the Layer-2 state-space walk in step B automatically via
  `run_gate`. The whole current production catalog is Tier 1, so this is the first
  real exercise of the Tier-2 path; if pilot Tier-2 skeletons prove expensive to
  validate, the supervisor may keep the remainder Tier 1 and record the decision.
- **Schema source of truth**: `storybook/models.py` (`ending.kind` / `ending.valence`),
  not the stale `reference/skeleton-format.md` field names; the format reference is
  used only for the `<<FILL role=... words=... beats='...'>>` directive grammar. Every
  non-ending node body is a `<<FILL>>` directive whose `words=` hint matches the
  band's ADR-011 mean and whose `beats=` text is specific enough for a Haiku/Sonnet
  author to fill without inventing plot.
- **Scripted validation (B)**, a Wave 0 addition `scripts/check_skeleton.py`:
  `load_skeleton()` (which already runs the gate's blocking layers on the shell) plus
  assertions the gate alone does not pin to the brief: declared cell matches the
  brief, node count inside `production_cell_budget`, shortest satisfying-completion
  path >= `min_complete_floor`, ending count inside the cell's ADR-011 range, topology
  declaration matches the brief, `production_eligible: true`, tier as briefed.
- **Design review rubric (C, Opus)**: beat-arc quality on the fastest-finish path
  (setup -> rising -> climax -> resolution, no hollow win), choice meaningfulness (no
  fake choices converging instantly without consequence), reconvergence reads sensibly
  from every parent, fail-state placement matches band policy, beats are fillable at
  the band's words-per-node mean, theme/topology diversity vs the cell's other
  skeletons.
- **Dagger-cell ceiling (deliberate experiment)**: ADR-011 flags 13-16 Long gamebook
  and 16+ Medium/Long gamebook as at or beyond the ~460-node hand-authoring ceiling.
  In each dagger cell, the two new skeletons split roles: **one targets the low end**
  of the node envelope (a safely authorable seed), and **one deliberately targets the
  upper half of the envelope** (for 16+ Long gamebook, ~600+ nodes) to empirically
  test the 460-node ceiling assumption. The ceiling-challenger's design report must
  record evidence for or against the ceiling: chunks needed, repair cycles, review
  findings density, and wall-clock/token cost relative to the low-end sibling, so
  ADR-011's ceiling number can be revisited with data.
- **Repair loop**: same bound as stories (section 7), except escalation has nowhere to
  go above Fable; a skeleton that fails twice is halted and reported with the reviewer
  findings.

## 7. Failure handling

- **Repair loop (bounded)**: on any failed check or rubric category, the original
  author agent receives only the findings and revises the cited nodes, prose only.
  Maximum **two repair cycles per story at the assigned model**; the third attempt
  escalates the failing nodes to Opus (section 3). If the Opus attempt also fails, the
  story is **halted** and reported, not force-passed.
- **Structural defects**: if a gate failure implicates the skeleton itself (topology,
  budget, ending-kind violations that prose cannot fix), the story is halted and the
  defect filed as a skeleton bug. Agents never mutate structure to make a gate pass.
- **Integrity failure**: a structural diff from an author agent is discarded and
  refilled from the pristine skeleton; the agent does not "fix" its own structural
  drift.

## 8. Import and publication (explicitly deferred)

`import_cli` requires a running Postgres and a `--family` UUID, and ADR-005 makes human
approval mandatory before anything reaches a child. Therefore this run stops at
committed artifacts. Follow-up (separate session, dev environment up):

```bash
uv run python -m cyo_adventure.generation.import_cli out/<slug>.filled.json --family <family-uuid>
```

run once per approved story, followed by guardian/admin review in the approval UI.
The import step re-runs the same gate server-side, so a story approved here should
import cleanly; any divergence is a bug worth catching.

## 9. Known discrepancy to fix in Wave 0

`.claude/skills/cyo-author/SKILL.md` step 2 lists words-per-node targets (3-5 ~75-100,
5-8 ~100, ..., 16+ ~250) that predate ADR-011 and **conflict with the enforced
envelopes** in `validator/band_profile.py` (3-5 mean 40 with a hard per-node max of 90,
5-8 mean 70/max 155, 8-11 and 10-13 mean 100/max 220, 13-16 prose mean 140/max 310,
16+ prose mean 175/max 385, gamebook 65/145 and 80/175). An author following the stale
SKILL.md numbers at 3-5 would trip the per-node hard max. Wave 0 updates SKILL.md to
the ADR-011 table; until then, agent prompts carry the correct numbers explicitly. The
per-node `words=` hints inside the skeletons already match ADR-011 and are the primary
per-node target.

## 10. Assumptions and risks

| # | Assumption / risk | Mitigation |
| :-: | --- | --- |
| 1 | Skeleton `words=` hints and structure are gate-consistent (skeletons were authored against ADR-011) | Wave 1 pilot verifies end-to-end before large spends |
| 2 | Haiku prose quality is sufficient for 3-5/5-8 | Sonnet reviewer + pilot in Wave 1; reassign band to Sonnet if pilot review fails on craft |
| 3 | Chunked filling (~30 nodes) preserves continuity across chunks | Stable preamble carries world notes; rubric category 5 checks it; reduce chunk size if pilot shows seams |
| 4 | `run_gate` offline matches server-side import validation | Same function is called by the import path; divergence is a bug, surfaced at import time |
| 5 | Wave 4 gamebook fills (up to 505 nodes) may exceed single-agent context | Chunking plus per-chunk agent handoff; decision deferred until Wave 4 is authorized |
| 6 | Token cost: ~196k words of prose for Waves 1-3, plus review passes | Smallest-first waves, Haiku on young bands, Opus escalation-only |
| 7 | Wave 5 is the largest single spend (~7,000 nodes of Fable graph design plus Opus reviews) | Dagger cells target envelope low ends; supervisor may pause the track mid-wave at any cell boundary; per-cell commits keep partial progress |
| 8 | Fable-designed Tier-2 skeletons may hit Layer-2 walk cost or novel gate failures (Tier-2 path untested at production scale) | Tier 2 capped at one of the two new skeletons per 10-13+ cell; fall back to Tier 1 on repeated failures and record the decision |
| 9 | Large gamebook skeleton JSONs (~300-460 nodes) may exceed a single designer-agent response | Designer emits the graph in chunks (topology outline first, then node batches); scripted validation stitches and verifies the assembled file |

## 11. Acceptance criteria (run-level)

- [ ] 14/14 offered age x length combinations have a story in `out/` that passes:
      structural integrity, zero `<<FILL` markers, `run_gate` not blocked, word-mean in
      the advisory band with no node over the per-node max.
- [ ] Every story has a compliance report with all 7 rubric categories passed (or a
      documented, supervisor-approved waiver, expected only for RL-13 advisories).
- [ ] Coverage summary grid committed and current.
- [ ] No skeleton or metadata was mutated by any author agent (integrity diffs clean).
- [ ] Any Opus escalation is documented with its trigger.
- [ ] Wave 5: 36 new skeletons committed (2 per production cell, catalog at 3 per
      cell), each passing `check_skeleton.py` and an Opus design review, with a design
      report under `out/reports/skeletons/` and topology/theme diversity satisfied
      within every cell.
- [ ] Nothing imported or published; ADR-005 human approval remains the next gate.
