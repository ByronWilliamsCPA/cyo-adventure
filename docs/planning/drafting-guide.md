---
title: "Story Drafting Guide"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Practical guide for authoring and generating branching stories that conform to the Storybook format and pass the validation gate."
tags:
  - planning
  - architecture
component: Development-Tools
source: "docs/planning/tech-spec.md sections Authoring Pipeline, Validation Gate, Story DSL; docs/planning/PROJECT-PLAN.md Phase 0 item P0-11"
---

# Story Drafting Guide

> **Status**: Active | **Version**: 0.2 | **Updated**: 2026-07-03

## Purpose

This guide is the reference document inserted into Stage A (Structure) and Stage B (Prose)
generation prompts as `{drafting_guide}`. It is also the practical handbook for a human
author writing stories by hand. Every section maps to a constraint that the validation
gate enforces, so following this guide is the fastest path to a story that passes on the
first attempt.

---

## Node and Depth Budgets

Node count and branch depth are enforced by the Layer-1 graph validator. The old fixed
per-band node-count ranges (for example "8-11 -> 15-30 nodes") are superseded by ADR-011's
story-scale framework: budgets are now a `band x length x style` matrix where length
(short / medium / long) is the primary driver and cells are total-words-driven. Do not
hardcode a node range from memory; the authoritative source is the per-cell envelope in
`validator/band_profile.py`, single-sourced there and described in
[ADR-011](./adr/adr-011-story-scale-framework.md).

- **Bands**: the six supported bands are "3-5", "5-8", "8-11", "10-13", "13-16", "16+".
- **Length x style**: each band crosses `length` (short / medium / long) and `style`
  (prose / gamebook); the resulting cell sets the node-count envelope and depth ceiling.
- **MVP / Test tier**: there is a non-production MVP/Test tier (`production_eligible =
  false`) with compact envelopes for pipeline testing; do not ship its output to readers.

"Node count" is the total number of `Node` records in the story, including all endings.
"Branch depth" is the longest path from `start_node` to any ending node, measured in
hops.

The validator fails stories that exceed the cell's upper bound. Stories below the lower
bound trigger a warning (not a hard failure), but very short stories rarely satisfy the
`ending_count` minimum of two distinct endings.

**Configuration cap**: for Tier-2 stories, keep the reachable state space below 100,000
configurations. A configuration is a `(node_id, var_state)` pair. To stay safely within
the cap with a 50-node story: use at most 2 boolean variables plus one integer variable
with a range of 0 to 5 (2 x 2 x 6 = 24 variable-state combinations; 50 x 24 = 1,200
reachable configurations, well within the cap). Add variables only when the story
requires them for gating; each new variable multiplies the configuration space.

---

## Branch-and-Bottleneck Structure

The recommended structure pattern for all age bands is `branch_and_bottleneck`. In this
pattern, the story fans out from choice points into distinct branches, then converges back
at bottleneck nodes before fanning out again. This keeps the story manageable for the LLM
and keeps the validator's reachability check tractable.

```text
start
  |
  +-- branch A ----+
  |                 +--> bottleneck 1 --> ...
  +-- branch B ----+
```

**Why bottlenecks matter**: without them, the story becomes a full binary tree that doubles
in nodes at every level. A 6-level tree has 63 nodes; a 10-level tree has 1,023. Bottlenecks
let you write distinctive experiences on each branch while keeping total node count inside
the budget.

Other supported structure patterns (for the concept brief `structure_pattern` field):

- `time_cave`: the reader loops back to a central hub from multiple branches; useful for
  exploration stories. Every hub exit must lead toward an ending to pass the loop-escape
  check.
- `gauntlet`: a mostly linear sequence with a few decision points; suitable for the 8-11
  band where too many choices are overwhelming.
- `quest`: a multi-stage journey where each stage has its own branch-and-bottleneck; the
  stages connect in a fixed order.
- `loop_and_grow`: the reader may revisit nodes, with state tracking their progress across
  loops. Requires Tier 2; the loop-escape check requires that every cycle has an exit path
  to an ending.

Avoid fully symmetric trees (binary trees where every non-ending node has exactly two
choices): they produce the node-count explosion described above and do not generate well
because the LLM runs out of distinctive beats.

---

## Voice, Tense, and Perspective

All story prose is written in **second person, present tense**:

> You push open the heavy door. The corridor stretches ahead, lit by a single lantern
> hanging from the ceiling. To your left, a narrow staircase leads upward. To your right,
> water drips from a stone alcove.

Rules:

- Address the reader as "you," never "the protagonist" or a character name in body text
  (the protagonist name belongs in the concept brief only).
- Use present tense throughout, including flashbacks described as memories ("you remember
  the day you first...").
- Choice labels use the imperative or a description of the action ("Open the door" or
  "Go left toward the staircase"), not a question.
- Endings state what happens, do not ask what the reader wants to do next. Ending nodes
  have `is_ending: true` and zero choices.

---

## Age-Band Reading Levels

The `reading_level_target` field in the concept brief sets the Flesch-Kincaid grade target.
The validator checks against this target with the `tolerance` defined in the story metadata
(advisory warning only; the parent makes the final call).

| Age band | FK grade target | Guidance |
|----------|----------------|----------|
| 3-5 | 0.0 to 1.5 | Very short sentences (5-8 words average). Read-aloud cadence, repetition, and concrete nouns. Minimal abstraction. |
| 5-8 | 1.5 to 3.0 | Short sentences (8-12 words average). Simple vocabulary with gentle stretch words explained in context. |
| 8-11 | 3.0 to 4.5 | Short sentences (10-14 words average). Simple vocabulary. One idea per sentence. Concrete imagery. |
| 10-13 | 5.0 to 7.0 | Moderate sentence length (14-18 words average). Can introduce unfamiliar words if context makes them clear. |
| 13-16 | 7.0 to 9.5 | Longer sentences acceptable. Figurative language, irony, and ambiguous outcomes are age-appropriate. |
| 16+ | 9.5 to 12.0 | Adult-YA register. Complex syntax, layered themes, and morally ambiguous outcomes are acceptable. |

Node body length scales with the band and with the ADR-011 length / style cell. The
authoritative per-node envelope is the `_WORDS_PER_NODE` table in
`validator/band_profile.py`; do not hardcode from memory. As a story-mean advisory band
per that table, aim for roughly 28-55 words per node at 3-5, 50-95 at 5-8, 70-135 at both
8-11 and 10-13, 100-185 at 13-16, and 125-230 at 16+ (prose; gamebook nodes run shorter).
Each cell also sets a hard per-node maximum well above these advisory bands. Longer bodies
push the FK grade up and slow the reading experience; shorter bodies leave the story
feeling sparse.

---

## Tier-2 Variables and Conditions

The schema does not gate Tier-2 by age band: `metadata.tier` is any of 1 or 2, and the
only hard rule is that a Tier-1 story must not declare variables (`tier 1 stories must not
declare variables`). As an authoring guideline, reserve state-tracking (Tier-2) for the
bands where a reader can follow persistent state: the 8-11, 10-13, 13-16, and 16+ bands.
Keep the youngest bands (3-5 and 5-8) at Tier-1. Use variables sparingly at any band;
every variable multiplies the state space (see the configuration cap below).

**Variable rules**:

- Declare all variables in the `variables` block at the top of the story. Every variable
  must have a `name` (snake_case), a `type` (`bool` or `int`), an `initial` value, and a
  `description`.
- For `int` variables, always set `min` and `max`. The validator rejects any story where
  a reachable transition could push the variable past its bounds.
- Use booleans for flags ("has_lantern", "met_the_elder"). Use small integers for
  counters that matter ("courage", "supplies", "keys_found") with a range of 0 to 5 or
  0 to 3.
- v1 supports only `bool` and `int` variables. String and enum state are out of scope
  for v1; model categorical choices as a set of boolean flags instead.

**Condition rules** (the JSONLogic shape, restricted to 10 operators):

```json
// "you have the lantern"
{ "==": [ { "var": "has_lantern" }, true ] }

// "courage is at least 3 and you do not have the curse"
{ "and": [
  { ">=": [ { "var": "courage" }, 3 ] },
  { "!": { "var": "has_curse" } }
] }
```

Permitted operators: `var`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `and`, `or`, `!`.

Excluded (the validator rejects these): arithmetic (`+`, `-`, `*`, `/`, `%`), `in`,
string operators (`cat`, `substr`), array reductions, and `if`/ternary.

A choice whose condition is `false` is hidden from the reader entirely, not shown as
greyed out. Do not write conditions that you expect to be false for most readers;
a conditional choice that no reachable configuration can expose is flagged as a dead
branch by the Layer-2 validator.

**Effect rules**:

- Effects use `op: "set"`, `op: "inc"`, or `op: "dec"`.
- Place effects on choices (when a choice is made) or on node `on_enter` (when a node
  is entered). Use `on_enter` for "you arrive and find something"; use choice effects for
  "you take the action and gain something."
- Use `once: true` on `on_enter` effects that should apply only on the first visit:
  "you find the lantern" should not re-grant the lantern on every re-entry to the cellar
  node.
- Do not stack many effects on a single node or choice; the state explosion makes the
  story harder to repair.

---

## Endings

Every story must have at least two distinct endings. The validator counts endings as nodes
with `is_ending: true` and checks that `ending_count` in the metadata matches the actual
count of ending nodes.

Each ending node requires an `ending` block:

```json
{
  "id": "ending_sunrise",
  "type": "success",
  "title": "The sunrise ending"
}
```

The `id` is stable across prose edits and is the anchor for the ending tracker (Phase 4b).
Use a slug that describes the outcome, not a number ("ending_escape", "ending_captured",
"ending_befriended"), so it remains meaningful after the prose changes.

Ending types: `success`, `failure`, `bittersweet`, `open`. These are metadata only; the
validator does not restrict ending types. Use them to give the parent reviewer a quick
read on the emotional tone of each outcome.

---

## Concept Brief Field List

The concept brief is the structured input to Stage A. All fields are passed to the
generation prompt as `{concept_brief}`. Fields marked with `?` are optional.

| Field | Type | Description |
|-------|------|-------------|
| `title?` | string | Working title (optional; the LLM may propose one) |
| `premise` | string | One-paragraph description of the situation and stakes |
| `protagonist` | object | `name` (fictional), `age` (fictional), `role` (description) |
| `point_of_view` | enum | `"second_person"` (default and required for v1) |
| `age_band` | enum | one of `"3-5"`, `"5-8"`, `"8-11"`, `"10-13"`, `"13-16"`, `"16+"` |
| `reading_level_target` | object | `{ "scheme": "flesch_kincaid_grade", "target": 4.0, "tolerance": 0.5 }` |
| `tier` | int | `1` (branching only) or `2` (state-tracking) |
| `tone` | string | e.g. "adventurous", "gentle mystery", "tense survival" |
| `themes_allowed` | string[] | e.g. `["friendship", "courage", "nature"]` |
| `content_nogo` | string[] | e.g. `["graphic violence", "romantic content"]` |
| `target_node_count` | int | Target total node count (see budgets above) |
| `ending_count` | int | Number of distinct endings (minimum 2) |
| `structure_pattern` | enum | `time_cave`, `gauntlet`, `branch_and_bottleneck`, `quest`, `loop_and_grow` |
| `desired_variables[]?` | object[] | For Tier 2: each has `name`, `type`, `initial`, `min?`, `max?`, `description` |
| `special_constraints[]?` | string[] | Freeform constraints for the LLM; length-limited; no real PII |

`protagonist.name` must be a fictional name, not the name of any real child. The backend
validates this field does not match any `child_profile.display_name` before dispatching to
the provider.

---

## Common Validation Failures and How to Avoid Them

| Failure | Rule | Avoidance |
|---------|------|-----------|
| Orphan node | Reachability: BFS from start does not reach the node | Every node must be the `target` of at least one choice from a reachable node |
| Dead end | Stateful dead-end: a reachable configuration has zero visible choices | Ensure at least one choice is visible (its condition is true) at every reachable non-ending state |
| Dangling target | Reference integrity: `choice.target` names a node that does not exist | Do not generate or edit `target` values before the node list is finalized |
| Bound overflow | Condition consistency: a reachable `inc`/`dec` would exceed `min`/`max` | Set `max` and `min` conservatively; avoid incrementing a counter in a loop without a cap check |
| Configuration cap | State space exceeds 100,000 reachable configurations | Reduce variables; narrow integer ranges; use `branch_and_bottleneck` to converge |
| Dead branch | Conditional usefulness: a conditional choice is unreachable from any configuration | Remove the condition or redesign the variable assignments so the condition can be satisfied |
| No path to ending | Stateful termination: a reachable configuration has no path to any ending | Ensure every cycle has an exit; avoid conditions that permanently block the only exit choice |

---

## Related Documents

- [Tech Spec: Authoring Pipeline](./tech-spec.md#authoring-pipeline-staged-generation)
- [Tech Spec: Validation Gate](./tech-spec.md#validation-gate-deterministic-no-llm)
- [Tech Spec: Story Runtime Semantics](./tech-spec.md#story-runtime-semantics-v1)
- [Stage A Structure Prompt](./stage-prompts/structure.md)
- [Stage B Prose Prompt](./stage-prompts/prose.md)
- [Stage C Repair Prompt](./stage-prompts/repair.md)
- [ADR-001: JSON Storybook format](./adr/adr-001-story-format-json-storybook.md)
- [ADR-006: Conditions in-house evaluator](./adr/adr-006-conditions-inhouse-evaluator.md)
- [ADR-011: Story-scale framework (band x length x style)](./adr/adr-011-story-scale-framework.md)
