---
title: "Story Drafting Guide"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Practical guide for authoring and generating branching stories that conform to the Storybook format and pass the validation gate."
tags:
  - planning
  - architecture
component: Development-Tools
source: "docs/planning/tech-spec.md sections Authoring Pipeline, Validation Gate, Story DSL; docs/planning/PROJECT-PLAN.md Phase 0 item P0-11"
---

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

## Craft for Delight

Every section above this one is a constraint: a budget, a depth limit, a schema shape, what not to
change. This section is the positive half. Nothing here is enforced by the validator; it is
directed at the LLM and at a human author, and the kid-appeal design review found that a pipeline
optimized only for the sections above produces prose that is safe, on-budget, and flat (design
review section 2.4). Follow this section with the same seriousness as the budgets.

**A memorable recurring image.** Give every story one concrete, sensory image the reader meets
early and meets again, changed, before the story ends: a lantern that burns a different color the
second time, a paper boat that keeps returning, a nervous laugh that becomes a brave one. Choose it
at the concept-brief stage and thread it through every stage after. A recurring image is what a
child describes to a parent afterward ("the story with the boat"), not "chapter 3."

**A laugh per chapter or scene, at the young bands.** At `3-5`, `5-8`, and `8-11`, aim for at least
one moment of real, age-appropriate humor per chapter or major scene, plus one warm surprise (a
friendly reveal, an unexpected kindness, a small joke that pays off later). The generation pipeline
has no lever for this today except prose choices; reach for the humor and wonder variation axes in
`generation/variation.py` (`running_joke`, `awestruck_wonder`, `playful_figurative`,
`mischievous_narrator`) so a given story can lean toward funny or wondrous rather than defaulting
every story to sincere and safe.

**Sensory specificity native to the theme's world.** Generic sensory description ("it was cold,"
"the room smelled strange") reads as filler. Ground every scene in the sensory texture specific to
its setting and genre: a cave story smells of wet stone and bat guano, not "spooky"; a bakery story
smells of butter and scorched sugar, not "yummy." Pull the concrete, world-native detail from the
concept brief's `premise` and `themes_allowed` rather than reaching for a generic descriptor.

**A strong last line, on every ending.** The final sentence of an ending node is the last thing the
reader hears before the celebration screen. It should land as a complete beat, not trail off: name
the outcome's feeling, not only its fact. Compare "You made it home safely." (flat) to "You made it
home, and the porch light was already on, like someone knew you were coming." (lands).

**Every choice acknowledged in the immediately following prose.** This is the fill-gate rule from
ADR-011 section 10's cross-cutting rules (companion to the grammar table below), grounded in Fendt,
Harrison, Ware, Cardona-Rivera and Roberts (ICIDS 2012): felt agency comes from the acknowledgment,
not from the branch existing at all. The very first line after a choice must visibly register that
specific pick, even a "flavor" choice with no mechanical consequence. Not yet automated in this
pipeline as of this revision; hold the rule as you draft.

**At 3-5, rhythm and repetition beat Flesch-Kincaid compliance.** The 3-5 FK window (see the table
above) is the tightest of any band and, taken as a line-by-line target, produces choppy staccato
prose ("Clover is a little kitten. She sat in a sunny garden."). 3-5 prose is read *aloud* by an
adult, not decoded silently by the child; real picture-book prose favors longer rhythmic sentences,
repetition, refrain, and page-turn hooks over short declarative sentences (design review section
2.8). Draft for the ear first and treat the FK window as a loose ceiling, not a sentence-by-sentence
rule: a repeated refrain can push the mechanical grade up while making the passage easier, not
harder, for a 3- or 4-year-old to follow aloud.

### Per-band choice grammar (ADR-011 section 10)

Adopted 2026-08-01 as decision D15, companion to ADR-026's rendered-stop flow. A "stop" is one
rendered page the child lands on: a single node at `3-5`/`5-8`, a flowed multi-node passage from
`8-11` up.

| Band | Presentation | Choice cadence | Max choiceless stops in a row | Flavor vs consequential | Options per choice | Words per stop |
|------|--------------|-----------------|--------------------------------:|----------------------------|-----------------------|-------------------|
| 3-5 | discrete pages | every 2nd-4th page; scaffold interaction (predict, point, answer) elsewhere | 2-3 | ~90/10; consequences immediate and visible; reconvergence free | 2 | 10-40 |
| 5-8 | discrete pages | every 1st-2nd page | 2 | ~70/30; same-scene payoff | 2-3 | 30-70 |
| 8-11 | flowed prose | every stop ends in a choice | 1, prefer 0 | ~50/50; state-gated consequences begin, with a visible "noticed" cue | 3 | 60-135 |
| 10-13 | flowed prose | every stop ends in a choice | 0-1 | ~40/60; delayed, cross-scene consequences; distinct targets | 3 | 80-150 |
| 13-16 | flowed prose | every stop ends in a choice | 0-1 | ~30/70; consequence foreshadowed | 3-4 | 100-200 |
| 16+ | flowed prose | every stop ends in a choice | 0-1 | ~30/70; gamebook lethality per the section 5 shape | 3-4 | 100-230 |

Cross-cutting rules, all bands (ADR-011 section 10):

- Every choice is acknowledged in the immediately following prose (see above).
- Every interaction is story-congruent; none is decorative (Takacs, Swart and Bus 2015).
- From `8-11` up, design for replay detection of reconvergence: differing acknowledgment lines,
  visible state, so a re-read notices its own echo.
- Scaffold interactions at `3-5` (predict/answer beats that are not plot forks) are the approved
  mechanism for choiceless pages; they need a schema minor and their own prompt support, not yet
  shipped as of this revision.

This table governs **new** content under decision D15; it is not yet a validator hard rule
(enforcement lands per the kid-appeal implementation plan's `W2.1`). Grandfathered skeletons
authored before 2026-08-01 do not conform and are not a style reference.

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

## Related Documents

- [Tech Spec: Authoring Pipeline](./tech-spec.md#authoring-pipeline-staged-generation)
- [Tech Spec: Validation Gate](./tech-spec.md#validation-gate-deterministic-no-llm)
- [Tech Spec: Story Runtime Semantics](./tech-spec.md#story-runtime-semantics-v1)
- [Stage A Structure Prompt](./stage-prompts/structure.md)
- [Stage B Prose Prompt](./stage-prompts/prose.md)
- [Stage C Repair Prompt](./stage-prompts/repair.md)
- [ADR-001: JSON Storybook format](./adr/adr-001-story-format-json-storybook.md)
- [ADR-006: Conditions in-house evaluator](./adr/adr-006-conditions-inhouse-evaluator.md)
