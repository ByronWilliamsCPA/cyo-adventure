# Story Drafting Guide

> **Status**: Draft | **Version**: 0.2 | **Updated**: 2026-08-01

## Purpose

This guide is the reference document inserted into Stage A (Structure) and Stage B (Prose)
generation prompts as `{drafting_guide}`. It is also the practical handbook for a human
author writing stories by hand. Every section maps to a constraint that the validation
gate enforces, so following this guide is the fastest path to a story that passes on the
first attempt.

---

## Node and Depth Budgets

Node count and branch depth are enforced by the Layer-1 graph validator. Stay within these
ranges:

| Age band | Tier | Target node count | Max branch depth |
|----------|------|-------------------|------------------|
| 3-5 | 1 (branching only) | 8-20 nodes | 4 levels |
| 5-8 | 1 (branching only) | 12-30 nodes | 6 levels |
| 8-11 | 1 (branching only) | 15-30 nodes | 6 levels |
| 10-13 | 1 or 2 | 25-50 nodes | 8 levels |
| 13-16 | 1 or 2 | 30-60 nodes | 10 levels |
| 16+ | 1 or 2 | 30-60 nodes | 12 levels |

These band-level ranges are `validator/band_profile.py`'s `_PROFILES` table (the floor/ceiling the
gate enforces when a story is not scale-classified into an ADR-011 length/style cell). A
scale-classified story instead uses the narrower per-cell envelope from `_PRODUCTION_CELLS`
(ADR-011 section 5's master cell table, for example `8-11`/`short`/`prose` is 60-100 nodes, not the
band-level 15-30); consult that table directly when drafting to a declared length tier.

"Node count" is the total number of `Node` records in the story, including all endings.
"Branch depth" is the longest path from `start_node` to any ending node, measured in
hops.

The validator fails stories that exceed the upper bounds. Stories below the lower bound
trigger a warning (not a hard failure), but very short stories rarely satisfy the
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

**Second person, present tense, is the POV standard for every band, `3-5` through `16+`, with no
per-band exception.** This was ratified as decision D14 (design review section 8,
2026-08-01): "second person is the standard for all bands." There is no band where third person is
correct; a prior reading of this guide that implied otherwise for the young bands was never policy,
it was drift between the guide and an un-audited corpus (design review section 2.2).

> You push open the heavy door. The corridor stretches ahead, lit by a single lantern
> hanging from the ceiling. To your left, a narrow staircase leads upward. To your right,
> water drips from a stone alcove.

Rules, all bands:

- Address the reader as "you," never "the protagonist" or a character name in body text
  (the protagonist name belongs in the concept brief only, and is the hook a
  `personalizable` HERO slot binds to, where a skeleton declares one).
- Use present tense throughout, including flashbacks described as memories ("you remember
  the day you first...").
- Choice labels use the imperative or a description of the action ("Open the door" or
  "Go left toward the staircase"), not a question.
- Endings state what happens, do not ask what the reader wants to do next. Ending nodes
  have `is_ending: true` and zero choices.

**At 3-5**, the prose is read aloud by an adult, not decoded silently by the child; "you" still
addresses the child directly, present tense narrates what is happening to them right now, in the
story. Do not soften second person to a named third-person character to make the read-aloud voice
easier: "you" is what makes the story theirs, and read-aloud delivery does not require narrating
distance (design review sections 2.2 and 2.6).

**Enforcement**: this guide is prompt-side guidance only, as of this revision. A fill-gate check
that measures second-person density (the design review's own audit measured 15-57 "you" per 1,000
words in compliant books versus 0-6.6 in the third-person kid-band corpus) and rejects an
out-of-spec fill is a separate, later work item (`W2.3` in the kid-appeal implementation plan) and
is not active yet. Until it lands, follow this rule directly; do not treat the absence of an
automated gate as license to draft in third person.

**Existing catalog**: the 3-5/5-8/8-11 skeletons filled before 2026-08-01 are third person and are
grandfathered under decision D11: they stay readable, but a cell stops offering them for new
generation once a compliant (second-person) skeleton exists for that cell. They are not a style
reference for new fills.

---

## Age-Band Reading Levels

The `reading_level_target` field in the concept brief sets the Flesch-Kincaid grade target. The
validator checks against this target with the `tolerance` defined in the story metadata (advisory
warning only; the parent makes the final call).

| Age band | FK grade target | Target +/- tolerance | Guidance |
|----------|-----------------:|------------------------|----------|
| 3-5 | 1.0 | 0.0 to 2.0 | Very short, rhythmic sentences; heavy repetition. See "Craft for Delight" below: draft for the read-aloud ear before this window. |
| 5-8 | 2.0 | 1.0 to 3.0 | Short, simple sentences. Familiar vocabulary. One idea per sentence. |
| 8-11 | 4.0 | 3.0 to 5.0 | Short sentences (10-14 words average). Simple vocabulary. One idea per sentence. Concrete imagery. |
| 10-13 | 6.0 | 5.0 to 7.0 | Moderate sentence length (14-18 words average). Can introduce unfamiliar words if context makes them clear. |
| 13-16 | 8.0 | 7.0 to 9.0 | Longer sentences acceptable. Figurative language, irony, and ambiguous outcomes are age-appropriate. |
| 16+ | 10.0 | 9.0 to 11.0 | Full adult sentence variety. Figurative language, irony, moral ambiguity, and gamebook terseness (in the `gamebook` style) are all in bounds. |

Targets are `story_requests/brief.py`'s `_BAND_FK_TARGET` table (the FK-target source of record
used when a child's `reading_level_cap` is unset); the tolerance window applies
`storybook/models.py`'s `ReadingLevel.tolerance` default of `1.0`. See "Craft for Delight" below
for why the 3-5 window should not be drafted to as a literal, line-by-line target.

### Node body length

Node body length is governed by `validator/band_profile.py`'s words-per-node envelope (ADR-011
section 3): a story-level **mean**, checked as an advisory warning, plus a hard per-node **max**,
checked as an error. There is no hard per-node minimum: a one-line beat is legitimate.

| Age band | Style | Mean words/node | Advisory band | Per-node max |
|----------|-------|------------------:|-----------------|---------------:|
| 3-5 | prose | 40 | 28-55 | 90 |
| 5-8 | prose | 70 | 50-95 | 155 |
| 8-11 | prose | 100 | 70-135 | 220 |
| 10-13 | prose | 100 | 70-135 | 220 |
| 13-16 | prose | 140 | 100-185 | 310 |
| 13-16 | gamebook | 65 | 45-90 | 145 |
| 16+ | prose | 175 | 125-230 | 385 |
| 16+ | gamebook | 80 | 55-110 | 175 |

Aim for the advisory band as a story-wide average, not a per-node rule: a tense beat can run three
words, a setup node can legitimately run to the per-node max. Longer bodies push the FK grade up
and slow the reading experience; shorter bodies leave the story feeling sparse.

---

## Tier-2 Variables and Conditions

Tier-2 mechanics are available for the 10-13 and 13-16 bands. Use them sparingly; every
variable multiplies the state space.

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
  "kind": "success",
  "valence": "positive",
  "title": "The sunrise ending"
}
```

The `id` is stable across prose edits and is the anchor for the ending tracker (Phase 4b).
Use a slug that describes the outcome, not a number ("ending_escape", "ending_captured",
"ending_befriended"), so it remains meaningful after the prose changes.

Each ending is typed on two axes the schema enforces as closed sets: `kind`, what
mechanically happened (`success`, `setback`, `death`, `capture`, `completion`,
`discovery`), and `valence`, how it feels (`positive`, `neutral`, `negative`). Both are
required on every ending block. Choose the pair that best matches the outcome so the
parent reviewer gets a quick read on each ending.

---

## Concept Brief Field List

The concept brief is the structured input to Stage A. All fields are passed to the
generation prompt as `{concept_brief}`. Fields marked with `?` are optional.

| Field | Type | Description |
|-------|------|-------------|
| `title?` | string | Working title (optional; the LLM may propose one) |
| `premise` | string | One-paragraph description of the situation and stakes |
| `protagonist` | object | `name` (fictional), `age` (fictional), `role` (description) |
| `point_of_view` | string | Narrative POV; free text, default `"second"` (not an enum) |
| `age_band` | enum | `"3-5"`, `"5-8"`, `"8-11"`, `"10-13"`, `"13-16"`, or `"16+"` |
| `reading_level_target` | float | Target Flesch-Kincaid grade level, e.g. `4.0` |
| `tier` | int | `1` (branching only) or `2` (state-tracking) |
| `tone` | string | e.g. "adventurous", "gentle mystery", "tense survival" |
| `themes_allowed` | string[] | e.g. `["friendship", "courage", "nature"]` |
| `content_nogo` | string[] | e.g. `["graphic violence", "romantic content"]` |
| `target_node_count` | int | Target total node count (see budgets above) |
| `ending_count` | int | Number of distinct endings (minimum 2) |
| `structure_pattern` | enum | `time_cave`, `gauntlet`, `branch_and_bottleneck`, `quest`, `loop_and_grow` |
| `desired_variables[]?` | string[] | For Tier 2: bounded variable-name strings (1-200 chars each); no nested type/initial/min/max/description |
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
